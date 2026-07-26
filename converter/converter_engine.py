import os
import shutil
import subprocess
import threading
import concurrent.futures
from datetime import datetime

import pandas as pd
import pytesseract
from PIL import Image
from pdf2docx import Converter
from pdf2image import convert_from_path
from pdfminer.high_level import extract_text
from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE
from pptx.util import Inches
from PyPDF2 import PdfMerger, PdfReader, PdfWriter


# ========================
# 常量定义
# ========================
DEFAULT_IMAGE_DPI = (150, 150)       # 图片转 PDF 默认 DPI
PDF_TO_IMAGE_DPI = 300               # PDF 转图片 DPI
OCR_TIMEOUT_SECONDS = 60             # OCR 最大处理时间（秒）
SLIDE_WIDTH_INCHES = 16              # PPT 幻灯片宽度（16:9）
SLIDE_HEIGHT_INCHES = 9              # PPT 幻灯片高度（16:9）

# LibreOffice 转换锁（LibreOffice 实例不宜并发）
_libreoffice_lock = threading.Lock()


def _run_with_timeout(func, args=(), kwargs=None, timeout=OCR_TIMEOUT_SECONDS):
    """在独立线程中运行函数，支持超时（线程安全，替代 signal.SIGALRM）"""
    kwargs = kwargs or {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(func, *args, **kwargs)
        try:
            return future.result(timeout=timeout)
        except concurrent.futures.TimeoutError:
            raise TimeoutError("OCR处理超时")


class TimeoutError(Exception):
    """OCR处理超时异常"""
    pass


def _libreoffice_convert(input_path, output_dir, convert_filter=None):
    """
    使用 LibreOffice 进行文件格式转换（WSL/Linux 替代 COM 方案）

    需要系统安装 LibreOffice: sudo apt install libreoffice-core libreoffice-writer \
        libreoffice-calc libreoffice-impress

    Args:
        input_path: 源文件路径
        output_dir: 输出目录
        convert_filter: 可选的导出过滤器（如 "pdf", "docx"），默认自动识别

    Returns:
        输出文件路径，失败返回 None
    """
    try:
        abs_input = os.path.abspath(input_path)
        abs_output = os.path.abspath(output_dir)
        os.makedirs(abs_output, exist_ok=True)

        cmd = ['libreoffice', '--headless', '--norestore']
        if convert_filter:
            cmd.extend(['--convert-to', convert_filter])
        else:
            cmd.extend(['--convert-to', 'pdf'])
        cmd.extend(['--outdir', abs_output, abs_input])

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120  # 2分钟超时
        )

        if result.returncode != 0:
            print(f"LibreOffice转换失败 (ret {result.returncode}): {result.stderr}")
            return None

        # 解析输出路径：LibreOffice 自动将扩展名替换为 .pdf
        base = os.path.splitext(os.path.basename(input_path))[0]
        if convert_filter and '.' in convert_filter:
            out_ext = convert_filter
        else:
            out_ext = 'pdf'
        out_file = os.path.join(abs_output, f"{base}.{out_ext}")

        if os.path.exists(out_file):
            return out_file
        return None
    except subprocess.TimeoutExpired:
        print("LibreOffice转换超时")
        return None
    except Exception as e:
        print(f"LibreOffice转换异常: {e}")
        return None


class Function:
    """文件转换引擎（WSL/Linux 版 — 使用 LibreOffice 替代 COM）"""

    @staticmethod
    def word_to_pdf(wordPath, pdfPath):
        """
        Word 转 PDF
        使用 LibreOffice --headless，适用于 WSL/Linux
        系统要求: sudo apt install libreoffice-core libreoffice-writer
        """
        with _libreoffice_lock:
            try:
                output_dir = os.path.dirname(os.path.abspath(pdfPath))
                result = _libreoffice_convert(wordPath, output_dir, 'pdf')
                if result and os.path.exists(result):
                    # 如果 LibreOffice 输出的文件名不同，重命名为目标路径
                    if result != os.path.abspath(pdfPath):
                        shutil.move(result, pdfPath)
                    return True
                return False
            except Exception as e:
                print(f"Word转PDF失败: {e}")
                return False

    @staticmethod
    def md_to_pdf(mdPath, pdfPath):
        """
        Markdown 转 PDF
        策略: 先利用 markdown 库将 .md 解析为 HTML，
        再借助 LibreOffice 将 HTML 渲染并导出为 PDF
        """
        import markdown
        try:
            # 1. 读取 Markdown 内容
            with open(mdPath, 'r', encoding='utf-8') as f:
                md_content = f.read()

            # 2. Markdown → HTML（启用常用扩展）
            md_extensions = [
                'tables',         # 表格支持
                'fenced_code',    # 围栏代码块
                'codehilite',     # 代码高亮
                'toc',            # 目录
                'nl2br',          # 换行转 <br>
            ]
            html_body = markdown.markdown(md_content, extensions=md_extensions)

            # 3. 包装为完整 HTML 文档（添加基础样式）
            html_doc = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
body {{
    font-family: 'Noto Sans SC', 'DejaVu Sans', Arial, sans-serif;
    font-size: 14px;
    line-height: 1.8;
    color: #333;
    max-width: 900px;
    margin: 40px auto;
    padding: 0 20px;
}}
h1 {{ font-size: 26px; border-bottom: 2px solid #4A90D9; padding-bottom: 8px; }}
h2 {{ font-size: 22px; border-bottom: 1px solid #ddd; padding-bottom: 6px; }}
h3 {{ font-size: 18px; }}
h4 {{ font-size: 16px; }}
pre {{ background: #f5f5f5; padding: 12px; border-radius: 6px; overflow-x: auto; }}
code {{ background: #f0f0f0; padding: 2px 6px; border-radius: 3px; font-family: 'DejaVu Sans Mono', 'Courier New', monospace; }}
pre code {{ background: none; padding: 0; }}
table {{ border-collapse: collapse; width: 100%; margin: 12px 0; }}
th, td {{ border: 1px solid #ccc; padding: 8px 12px; text-align: left; }}
th {{ background: #eef5fc; }}
blockquote {{ border-left: 4px solid #4A90D9; padding-left: 16px; color: #666; margin: 12px 0; }}
img {{ max-width: 100%; }}
</style>
</head>
<body>
{html_body}
</body>
</html>"""

            # 4. 写入临时 HTML 文件
            html_path = mdPath + '.tmp.html'
            with open(html_path, 'w', encoding='utf-8') as f:
                f.write(html_doc)

            # 5. 使用 LibreOffice 将 HTML 转为 PDF
            with _libreoffice_lock:
                output_dir = os.path.dirname(os.path.abspath(pdfPath))
                result = _libreoffice_convert(html_path, output_dir, 'pdf')

            # 6. 清理临时 HTML 文件
            try:
                os.remove(html_path)
            except Exception:
                pass

            if result and os.path.exists(result):
                if result != os.path.abspath(pdfPath):
                    shutil.move(result, pdfPath)
                return True
            return False
        except Exception as e:
            print(f"MD转PDF失败: {e}")
            # 清理可能残留的临时文件
            html_path = mdPath + '.tmp.html'
            if os.path.exists(html_path):
                try:
                    os.remove(html_path)
                except Exception:
                    pass
            return False

    @staticmethod
    def excel_to_pdf(excelPath, pdfPath):
        """
        Excel 转 PDF
        使用 LibreOffice，适用于 WSL/Linux
        系统要求: sudo apt install libreoffice-core libreoffice-calc
        """
        with _libreoffice_lock:
            try:
                output_dir = os.path.dirname(os.path.abspath(pdfPath))
                result = _libreoffice_convert(excelPath, output_dir, 'pdf')
                if result and os.path.exists(result):
                    if result != os.path.abspath(pdfPath):
                        shutil.move(result, pdfPath)
                    return True
                return False
            except Exception as e:
                print(f"Excel转PDF失败: {e}")
                return False

    @staticmethod
    def ppt_to_pdf(pptPath, pdfPath):
        """
        PPT 转 PDF
        使用 LibreOffice，适用于 WSL/Linux
        系统要求: sudo apt install libreoffice-core libreoffice-impress
        """
        with _libreoffice_lock:
            try:
                output_dir = os.path.dirname(os.path.abspath(pdfPath))
                result = _libreoffice_convert(pptPath, output_dir, 'pdf')
                if result and os.path.exists(result):
                    if result != os.path.abspath(pdfPath):
                        shutil.move(result, pdfPath)
                    return True
                return False
            except Exception as e:
                print(f"PPT转PDF失败: {e}")
                return False

    @staticmethod
    def html_to_pdf(htmlPath, pdfPath):
        """
        HTML 转 PDF
        使用 LibreOffice 渲染，适用于 WSL/Linux
        """
        with _libreoffice_lock:
            try:
                output_dir = os.path.dirname(os.path.abspath(pdfPath))
                result = _libreoffice_convert(htmlPath, output_dir, 'pdf')
                if result and os.path.exists(result):
                    if result != os.path.abspath(pdfPath):
                        shutil.move(result, pdfPath)
                    return True
                return False
            except Exception as e:
                print(f"HTML转PDF失败: {e}")
                return False

    @staticmethod
    def pdf_to_word(pdfPath, wordPath):
        """PDF 转 Word（使用 pdf2docx，跨平台）"""
        try:
            cv = Converter(pdfPath)
            cv.convert(wordPath, start=0, end=None)
            cv.close()
            return True
        except Exception as e:
            print(f"PDF转Word失败: {e}")
            return False

    @staticmethod
    def image_to_pdf(imagePath, pdfPath):
        """图片 转 PDF（逐张处理，避免内存OOM）"""
        try:
            import re
            image_files = []
            for file in os.listdir(imagePath):
                if file.lower().endswith(('.jpg', '.jpeg', '.png')):
                    image_files.append(os.path.join(imagePath, file))
            if not image_files:
                return False

            # 使用自然排序
            def natural_sort_key(s):
                return [int(text) if text.isdigit() else text.lower()
                        for text in re.split(r'(\d+)', os.path.basename(s))]
            image_files.sort(key=natural_sort_key)

            # 逐张处理，不一次加载所有图片到内存
            first_img = Image.open(image_files[0]).convert('RGB')
            if len(image_files) == 1:
                first_img.save(pdfPath, format='PDF', dpi=DEFAULT_IMAGE_DPI)
                first_img.close()
            else:
                # 逐张打开、添加、关闭
                rest_images = []
                for img_path in image_files[1:]:
                    img = Image.open(img_path).convert('RGB')
                    rest_images.append(img)
                first_img.save(
                    pdfPath, format='PDF', dpi=DEFAULT_IMAGE_DPI,
                    save_all=True, append_images=rest_images
                )
                first_img.close()
                for img in rest_images:
                    img.close()
            return True
        except Exception as e:
            print(f"图片转PDF失败: {e}")
            return False

    @staticmethod
    def pdf_to_image(pdfPath, imageDir):
        """PDF 转 图片"""
        try:
            pages = convert_from_path(pdfPath, 150)
            for index, img in enumerate(pages):
                img.save(
                    os.path.join(imageDir, 'page_%s.jpg' % (index + 1)), 'JPEG'
                )
            return True
        except Exception as e:
            print(f"PDF转图片失败: {e}")
            return False

    @staticmethod
    def csv_to_excel(csvPath, excelPath):
        """CSV 转 Excel"""
        try:
            # 不强制设置 index_col，保留原始数据结构
            data = pd.read_csv(csvPath)
            data.to_excel(excelPath, index=False)
            return True
        except Exception as e:
            print(f"CSV转Excel失败: {e}")
            return False

    @staticmethod
    def excel_to_csv(excelPath, csvPath):
        """Excel 转 CSV"""
        try:
            # 不强制设置 index_col，保留原始数据结构
            data = pd.read_excel(excelPath)
            data.to_csv(csvPath, encoding='utf-8', index=False)
            return True
        except Exception as e:
            print(f"Excel转CSV失败: {e}")
            return False

    @staticmethod
    def _ocr_pdf_pages(pdfPath):
        """OCR 辅助：将PDF页转图片后识别文字（在独立线程中运行）"""
        pages = convert_from_path(pdfPath, 300)
        text = ""
        for page in pages:
            text += pytesseract.image_to_string(
                page, lang='chi_sim+eng'
            ) + "\n"
        return text

    @staticmethod
    def pdf_ocr(pdfPath, outputPath):
        """PDF OCR 文字识别（带线程池超时控制，跨平台线程安全）"""
        try:
            text = extract_text(pdfPath)
            if len(text.strip()) < 10:
                text = _run_with_timeout(
                    Function._ocr_pdf_pages,
                    args=(pdfPath,),
                    timeout=OCR_TIMEOUT_SECONDS
                )
            with open(outputPath, 'w', encoding='utf-8') as f:
                f.write(text)
            return True
        except TimeoutError:
            print("PDF OCR超时")
            return False
        except Exception as e:
            print(f"PDF OCR失败: {e}")
            return False

    @staticmethod
    def _ocr_single_image(image_path):
        """OCR 辅助：识别单张图片文字（在独立线程中运行）"""
        return pytesseract.image_to_string(
            Image.open(image_path), lang='chi_sim+eng'
        )

    @staticmethod
    def image_ocr(imagePath, outputPath):
        """图片 OCR 文字识别（带线程池超时控制，跨平台线程安全）"""
        try:
            if os.path.isfile(imagePath):
                text = _run_with_timeout(
                    Function._ocr_single_image,
                    args=(imagePath,),
                    timeout=OCR_TIMEOUT_SECONDS
                )
                with open(outputPath, 'w', encoding='utf-8') as f:
                    f.write(text)
                return True
            elif os.path.isdir(imagePath):
                all_text = ""
                for file in os.listdir(imagePath):
                    if file.lower().endswith(('.jpg', '.jpeg', '.png')):
                        img_path = os.path.join(imagePath, file)
                        text = _run_with_timeout(
                            Function._ocr_single_image,
                            args=(img_path,),
                            timeout=OCR_TIMEOUT_SECONDS
                        )
                        all_text += f"=== {file} ===\n{text}\n\n"
                if all_text:
                    with open(outputPath, 'w', encoding='utf-8') as f:
                        f.write(all_text)
                    return True
                return False
            return False
        except TimeoutError:
            print("图片 OCR超时")
            return False
        except Exception as e:
            print(f"图片OCR失败: {e}")
            return False

    @staticmethod
    def img_to_ppt(imageDir, pptPath):
        """图片 转 PPT"""
        try:
            supported_formats = ('.png', '.jpg', '.jpeg', '.bmp', '.gif', '.tiff')
            image_files = []
            for file in os.listdir(imageDir):
                if file.lower().endswith(supported_formats):
                    image_files.append(os.path.join(imageDir, file))

            if not image_files:
                return False

            # 使用自然排序
            import re
            def natural_sort_key(s):
                return [int(text) if text.isdigit() else text.lower()
                        for text in re.split(r'(\d+)', os.path.basename(s))]
            image_files.sort(key=natural_sort_key)

            prs = Presentation()
            prs.slide_width = Inches(SLIDE_WIDTH_INCHES)
            prs.slide_height = Inches(SLIDE_HEIGHT_INCHES)

            # 第一张作为封面
            first_image = image_files[0]
            title_slide_layout = prs.slide_layouts[0]
            slide = prs.slides.add_slide(title_slide_layout)
            for shape in slide.placeholders:
                element = shape.element
                parent = element.getparent()
                parent.remove(element)
            background = slide.shapes.add_shape(
                MSO_SHAPE.RECTANGLE, 0, 0, prs.slide_width, prs.slide_height
            )
            background.fill.background()
            pic = slide.shapes.add_picture(
                first_image, 0, 0,
                width=prs.slide_width, height=prs.slide_height
            )

            # 剩余图片
            for image_file in image_files[1:]:
                slide = prs.slides.add_slide(prs.slide_layouts[5])
                for shape in slide.placeholders:
                    element = shape.element
                    parent = element.getparent()
                    parent.remove(element)
                background = slide.shapes.add_shape(
                    MSO_SHAPE.RECTANGLE, 0, 0, prs.slide_width, prs.slide_height
                )
                background.fill.background()
                slide.shapes.add_picture(
                    image_file, 0, 0,
                    width=prs.slide_width, height=prs.slide_height
                )

            prs.save(pptPath)
            return True
        except Exception as e:
            print(f"图片转PPT失败: {e}")
            return False

    @staticmethod
    def merge_pdf(pdf_list, output_path):
        """合并 PDF"""
        try:
            merger = PdfMerger()
            for pdf in pdf_list:
                merger.append(pdf)
            merger.write(output_path)
            merger.close()
            return True
        except Exception as e:
            print(f"合并PDF失败: {e}")
            return False

    @staticmethod
    def pdf_encrypt(pdfPath, outputPath, password):
        """PDF 加密：设置打开密码保护"""
        try:
            reader = PdfReader(pdfPath)
            if reader.is_encrypted:
                print("PDF已加密，请先解密后再加密")
                return False

            writer = PdfWriter()
            for page in reader.pages:
                writer.add_page(page)

            # 复制元数据
            if reader.metadata:
                writer.add_metadata(reader.metadata)

            writer.encrypt(user_password=password)

            with open(outputPath, 'wb') as f:
                writer.write(f)
            return True
        except Exception as e:
            print(f"PDF加密失败: {e}")
            return False

    @staticmethod
    def pdf_decrypt(pdfPath, outputPath, password):
        """PDF 解密：去除密码保护"""
        try:
            reader = PdfReader(pdfPath)

            if reader.is_encrypted:
                result = reader.decrypt(password)
                if result == 0:
                    print("PDF解密失败：密码错误")
                    return False

            writer = PdfWriter()
            for page in reader.pages:
                writer.add_page(page)

            # 复制元数据
            if reader.metadata:
                writer.add_metadata(reader.metadata)

            with open(outputPath, 'wb') as f:
                writer.write(f)
            return True
        except Exception as e:
            print(f"PDF解密失败: {e}")
            return False

    # ==========================================================
    # 压缩 / 解压 / 去密
    # ==========================================================

    @staticmethod
    def compress_zip(input_paths, output_path, password=None, arcnames=None):
        """压缩为 ZIP（可选密码加密），arcnames 为原始文件名列表"""
        try:
            names = arcnames or [os.path.basename(p) for p in input_paths]
            if password:
                import pyzipper
                with pyzipper.AESZipFile(output_path, 'w',
                                          encryption=pyzipper.WZ_AES) as zf:
                    zf.setpassword(password.encode('utf-8'))
                    for path, name in zip(input_paths, names):
                        zf.write(path, name)
            else:
                import zipfile
                with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                    for path, name in zip(input_paths, names):
                        zf.write(path, name)
            return True
        except Exception as e:
            print(f"ZIP压缩失败: {e}")
            return False

    @staticmethod
    def compress_targz(input_paths, output_path, arcnames=None):
        """压缩为 TAR.GZ（不支持加密），arcnames 为原始文件名列表"""
        try:
            import tarfile
            names = arcnames or [os.path.basename(p) for p in input_paths]
            with tarfile.open(output_path, 'w:gz') as tf:
                for path, name in zip(input_paths, names):
                    tf.add(path, arcname=name)
            return True
        except Exception as e:
            print(f"TAR.GZ压缩失败: {e}")
            return False

    @staticmethod
    def compress_7z(input_paths, output_path, password=None, arcnames=None):
        """压缩为 7Z（可选 AES-256 加密），arcnames 为原始文件名列表"""
        try:
            import py7zr
            names = arcnames or [os.path.basename(p) for p in input_paths]
            if password:
                with py7zr.SevenZipFile(output_path, 'w',
                                         password=password) as szf:
                    for path, name in zip(input_paths, names):
                        szf.write(path, name)
            else:
                with py7zr.SevenZipFile(output_path, 'w') as szf:
                    for path, name in zip(input_paths, names):
                        szf.write(path, name)
            return True
        except Exception as e:
            print(f"7Z压缩失败: {e}")
            return False

    @staticmethod
    def is_archive_encrypted(path):
        """检测压缩包是否加密（快速检查，不提取内容）"""
        fname = path.lower()
        try:
            if fname.endswith('.zip'):
                import zipfile
                with zipfile.ZipFile(path, 'r') as zf:
                    for info in zf.infolist():
                        if info.flag_bits & 0x1:
                            return True
                return False
            elif fname.endswith('.7z'):
                import py7zr
                try:
                    with py7zr.SevenZipFile(path, 'r') as szf:
                        return szf.needs_password()
                except Exception:
                    return False
            return False
        except Exception as e:
            print(f"检测加密状态失败: {e}")
            return False

    @staticmethod
    def decompress_archive(input_path, output_dir, password=None):
        """解压压缩包（自动识别格式）"""
        fname = input_path.lower()
        try:
            if fname.endswith('.zip'):
                if password:
                    # 加密 ZIP 需用 pyzipper（支持 AES）
                    import pyzipper
                    with pyzipper.AESZipFile(input_path, 'r') as zf:
                        zf.setpassword(password.encode('utf-8'))
                        zf.extractall(output_dir)
                else:
                    import zipfile
                    with zipfile.ZipFile(input_path, 'r') as zf:
                        zf.extractall(output_dir)
                return True
            elif fname.endswith('.tar.gz') or fname.endswith('.tgz') or fname.endswith('.tar'):
                import tarfile
                with tarfile.open(input_path, 'r:*') as tf:
                    tf.extractall(output_dir)
                return True
            elif fname.endswith('.7z'):
                import py7zr
                with py7zr.SevenZipFile(input_path, 'r',
                                        password=password) as szf:
                    szf.extractall(output_dir)
                return True
            else:
                print(f"不支持的解压格式: {input_path}")
                return False
        except Exception as e:
            print(f"解压失败: {e}")
            return False

    @staticmethod
    def decrypt_archive(input_path, output_path, password):
        """去除压缩包密码保护（解压后重新打包为无密码 ZIP）"""
        import tempfile
        import shutil
        temp_dir = tempfile.mkdtemp()
        try:
            # 用密码解压
            if not Function.decompress_archive(input_path, temp_dir, password):
                return False
            # 收集所有解压出的文件
            extracted = []
            for root, _dirs, files in os.walk(temp_dir):
                for f in files:
                    extracted.append(os.path.join(root, f))
            if not extracted:
                return False
            # 重新打包为无密码 ZIP
            import zipfile
            with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                for file_path in extracted:
                    arcname = os.path.relpath(file_path, temp_dir)
                    zf.write(file_path, arcname)
            return True
        except Exception as e:
            print(f"压缩包去密失败: {e}")
            return False
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
