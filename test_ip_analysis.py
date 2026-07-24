"""
IP访问分析与封禁功能测试脚本
"""
import requests
import time
from datetime import datetime

# 配置
BASE_URL = "http://localhost:5000"


def test_ip_logging():
    """测试IP访问记录功能"""
    print("=" * 60)
    print("测试1: IP访问记录功能")
    print("=" * 60)
    
    # 发送几个请求
    endpoints = [
        "/",
        "/login",
        "/register",
    ]
    
    for endpoint in endpoints:
        try:
            response = requests.get(f"{BASE_URL}{endpoint}")
            print(f"✓ 请求 {endpoint}: 状态码 {response.status_code}")
        except Exception as e:
            print(f"✗ 请求 {endpoint} 失败: {e}")
        time.sleep(0.5)
    
    print("\n提示: 请检查数据库 ip_access_logs 表是否有新记录\n")


def test_ip_blocking():
    """测试IP封禁功能"""
    print("=" * 60)
    print("测试2: IP封禁功能")
    print("=" * 60)
    
    # 注意: 这个测试需要管理员权限
    print("警告: 此测试需要管理员登录，请手动测试")
    print("\n测试步骤:")
    print("1. 以管理员身份登录系统")
    print("2. 访问 /admin/ip_analysis")
    print("3. 在IP排行榜中选择一个IP")
    print("4. 点击'封禁'按钮")
    print("5. 填写封禁原因和天数")
    print("6. 确认封禁")
    print("7. 使用被封禁的IP访问网站，应该返回403错误\n")


def test_statistics():
    """测试统计功能"""
    print("=" * 60)
    print("测试3: IP统计分析功能")
    print("=" * 60)
    
    print("请访问以下URL查看统计数据（需要管理员权限）:")
    print(f"  - 最近1小时: {BASE_URL}/admin/ip_analysis?hours=1")
    print(f"  - 最近24小时: {BASE_URL}/admin/ip_analysis?hours=24")
    print(f"  - 最近7天: {BASE_URL}/admin/ip_analysis?hours=168")
    print()


def test_api_endpoints():
    """测试API端点"""
    print("=" * 60)
    print("测试4: API端点测试")
    print("=" * 60)
    
    print("可用的API端点:")
    print(f"  POST {BASE_URL}/admin/block_ip - 封禁IP")
    print(f"  POST {BASE_URL}/admin/unblock_ip - 解封IP")
    print(f"  GET  {BASE_URL}/admin/ip_analysis - IP分析页面")
    print()


def main():
    """主函数"""
    print("\n")
    print("╔" + "=" * 58 + "╗")
    print("║" + " " * 10 + "IP访问分析与封禁功能测试" + " " * 22 + "║")
    print("╚" + "=" * 58 + "╝")
    print()
    
    # 检查服务器是否运行
    try:
        response = requests.get(BASE_URL, timeout=2)
        print(f"✓ 服务器正在运行 (状态码: {response.status_code})\n")
    except requests.exceptions.ConnectionError:
        print("✗ 无法连接到服务器")
        print(f"  请确保服务器在 {BASE_URL} 运行")
        print("  运行命令: python app.py\n")
        return
    except Exception as e:
        print(f"✗ 连接测试失败: {e}\n")
        return
    
    # 执行测试
    test_ip_logging()
    test_statistics()
    test_api_endpoints()
    test_ip_blocking()
    
    print("=" * 60)
    print("测试完成！")
    print("=" * 60)
    print("\n下一步:")
    print("1. 访问 http://localhost:5000/admin")
    print("2. 点击 'IP分析' 按钮")
    print("3. 查看访问统计数据和图表")
    print("4. 测试封禁/解封功能")
    print()


if __name__ == "__main__":
    main()
