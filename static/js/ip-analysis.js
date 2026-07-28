// ===== 读取 data 属性 =====
var _ipPanel = document.getElementById('ipAnalysisPanel');
function ipUrl(key) { return _ipPanel ? _ipPanel.getAttribute(key) : ''; }

// ===== 读取服务端渲染的 timeline 数据 =====
var _tlEl = document.getElementById('ip-timeline-data');
var timelineDataRaw = [];
try { if (_tlEl) { var d = JSON.parse(_tlEl.textContent.trim()); if (d && d !== 'null') timelineDataRaw = d; } } catch(e) {}
// ========== 坐标转换（WGS-84 → GCJ-02 火星坐标系） ==========
var pi = 3.1415926535897932384626;
var a = 6378245.0;
var ee = 0.00669342162296594323;

function transformLat(x, y) {
    var ret = -100.0 + 2.0 * x + 3.0 * y + 0.2 * y * y + 0.1 * x * y + 0.2 * Math.sqrt(Math.abs(x));
    ret += (20.0 * Math.sin(6.0 * x * pi) + 20.0 * Math.sin(2.0 * x * pi)) * 2.0 / 3.0;
    ret += (20.0 * Math.sin(y * pi) + 40.0 * Math.sin(y / 3.0 * pi)) * 2.0 / 3.0;
    ret += (160.0 * Math.sin(y / 12.0 * pi) + 320.0 * Math.sin(y * pi / 30.0)) * 2.0 / 3.0;
    return ret;
}

function transformLon(x, y) {
    var ret = 300.0 + x + 2.0 * y + 0.1 * x * x + 0.1 * x * y + 0.1 * Math.sqrt(Math.abs(x));
    ret += (20.0 * Math.sin(6.0 * x * pi) + 20.0 * Math.sin(2.0 * x * pi)) * 2.0 / 3.0;
    ret += (20.0 * Math.sin(x * pi) + 40.0 * Math.sin(x / 3.0 * pi)) * 2.0 / 3.0;
    ret += (150.0 * Math.sin(x / 12.0 * pi) + 300.0 * Math.sin(x / 30.0 * pi)) * 2.0 / 3.0;
    return ret;
}

function wgs84ToGcj02(wgsLat, wgsLng) {
    var dlat = transformLat(wgsLng - 105.0, wgsLat - 35.0);
    var dlng = transformLon(wgsLng - 105.0, wgsLat - 35.0);
    var radlat = wgsLat / 180.0 * pi;
    var magic = Math.sin(radlat);
    magic = 1 - ee * magic * magic;
    var sqrtmagic = Math.sqrt(magic);
    dlat = (dlat * 180.0) / ((a * (1 - ee)) / (magic * sqrtmagic) * pi);
    dlng = (dlng * 180.0) / (a / sqrtmagic * Math.cos(radlat) * pi);
    return { lat: wgsLat + dlat, lng: wgsLng + dlng };
}
// ========== 地图初始化 ==========
let map = null;
let markers = [];
let mapInitialized = false;

document.addEventListener('DOMContentLoaded', function() {
    // 延迟初始化地图和图表，等待DOM完全渲染且外部库加载完毕
    var attempts = 0;
    function tryInit() {
        attempts++;
        if (typeof L !== 'undefined' && typeof Chart !== 'undefined') {
            initMap();
            initTrendChart();
        } else if (attempts < 20) {
            setTimeout(tryInit, 100);
        } else {
            console.error('Leaflet 或 Chart.js 加载超时');
        }
    }
    // 非阻塞初始化，等待库加载完成
    setTimeout(tryInit, 50);
});

function initMap() {
    // 清除上次的地图实例
    if (map) {
        map.remove();
        map = null;
        markers = [];
    }
    
    console.log('开始初始化地图...');
    
    if (typeof L === 'undefined') {
        console.error('Leaflet 库加载失败！');
        showMapError('地图库加载失败，请刷新页面重试');
        return;
    }
    
    var mapDiv = document.getElementById('ipMap');
    if (!mapDiv) return;
    
    try {
        // 清空容器
        mapDiv.innerHTML = '';
        
        // 创建地图实例
        map = L.map(mapDiv, {
            center: [35.8617, 104.1954],
            zoom: 4,
            zoomControl: true
        });
        
        // 多源瓦片加载，自动切换（高德→CartoDB→OSM）
        var tileSources = [
            {
                name: '高德地图',
                url: 'https://webrd0{s}.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=8&x={x}&y={y}&z={z}',
                opts: { maxZoom: 18, minZoom: 1, attribution: '© 高德地图', subdomains: ['1','2','3','4'] }
            },
            {
                name: 'CartoDB',
                url: 'https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png',
                opts: { maxZoom: 19, attribution: '© CartoDB', subdomains: 'abcd' }
            },
            {
                name: 'OpenStreetMap',
                url: 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
                opts: { maxZoom: 19, attribution: '© OpenStreetMap', subdomains: 'abc' }
            }
        ];
        
        var tileIdx = 0;
        var tileLayer;
        var tileLoaded = false;
        
        function loadTileSource(index) {
            if (index >= tileSources.length) {
                console.warn('所有瓦片源均尝试失败');
                return;
            }
            if (tileLayer) { map.removeLayer(tileLayer); tileLayer = null; }
            
            var src = tileSources[index];
            console.log('尝试瓦片源[' + index + ']:', src.name);
            
            tileLoaded = false;
            tileLayer = L.tileLayer(src.url, src.opts);
            
            // 任一瓦片加载成功即标记
            tileLayer.on('load', function() {
                tileLoaded = true;
                console.log('✓ 瓦片加载成功:', src.name);
            });
            
            tileLayer.addTo(map);
            
            // 5秒后检查是否加载成功，否则切换
            setTimeout(function() {
                if (!tileLoaded) {
                    console.warn(src.name + ' 加载超时，切换到下一个');
                    loadTileSource(index + 1);
                }
            }, 5000);
        }
        loadTileSource(0);
        
        console.log('地图初始化成功（高德底图）');
        mapInitialized = true;
        
        // 强制刷新地图
        setTimeout(function() {
            map.invalidateSize();
            loadIpMapData();
        }, 500);
    } catch (error) {
        console.error('地图初始化错误:', error);
        showMapError('地图初始化失败: ' + error.message);
    }
}

function showMapError(msg) {
    var el = document.getElementById('ipMap');
    if (el) {
        el.textContent = '';
        var container = document.createElement('div');
        container.style.cssText = 'display:flex;align-items:center;justify-content:center;height:100%;color:#ff6b6b;';
        var icon = document.createElement('i');
        icon.className = 'fas fa-exclamation-triangle fa-2x me-3';
        container.appendChild(icon);
        var textDiv = document.createElement('div');
        var h5 = document.createElement('h5');
        h5.textContent = msg;
        textDiv.appendChild(h5);
        container.appendChild(textDiv);
        el.appendChild(container);
    }
}

function loadIpMapData() {
    var hours = parseInt(_ipPanel.getAttribute('data-hours')) || 24;
    console.log('加载IP地图数据, hours:', hours);
    
    fetch(ipUrl('data-map-url') + '?hours=' + hours)
        .then(function(resp) { return resp.json(); })
        .then(function(result) {
            console.log('地图数据返回:', result);
            if (result.success) {
                displayIpMarkers(result.data);
            } else {
                showMapError(result.message || '获取数据失败');
            }
        })
        .catch(function(err) {
            console.error('请求失败:', err);
            showMapError('网络请求失败');
        });
}

function displayIpMarkers(ipData) {
    if (!map) return;
    
    // 清除旧标记
    markers.forEach(function(m) { map.removeLayer(m); });
    markers = [];
    
    // 无数据
    if (!ipData || ipData.length === 0) {
        map.setView([35.8617, 104.1954], 4);
        L.popup()
            .setLatLng([35.8617, 104.1954])
            .setContent('<div style="text-align:center;font-size:14px;">暂无IP地理位置数据<br><small>请点击「刷新IP位置」获取<br>(本地开发时内网IP无法定位公网位置)</small></div>')
            .openOn(map);
        return;
    }
    
    // 添加标记
    console.log('绘制标记数量:', ipData.length);
    ipData.forEach(function(ip) {
        // 跳过内网IP（不在地图上显示，避免位置错误）
        if (ip.country === '内网' && ip.city === '本地网络') {
            console.log('跳过内网IP:', ip.ip_address);
            return;
        }
        if (ip.latitude !== null && ip.longitude !== null && parseFloat(ip.latitude) !== 0 && parseFloat(ip.longitude) !== 0) {
            var wgsLat = parseFloat(ip.latitude);
            var wgsLng = parseFloat(ip.longitude);
            var gcj = wgs84ToGcj02(wgsLat, wgsLng);
            
            var color = getColorByCount(ip.visit_count);
            var size = Math.min(36, Math.max(24, 12 + ip.visit_count / 2));
            
            // 自定义漂亮的定位图标
            var icon = L.divIcon({
                className: '',
                html: '<div style="position:relative;width:' + size + 'px;height:' + size + 'px;">' +
                      '<svg viewBox="0 0 24 36" width="' + size + '" height="' + (size * 1.4) + '">' +
                      '<defs><linearGradient id="g' + ip.ip_address.replace(/\./g,'') + '" x1="0%" y1="0%" x2="0%" y2="100%">' +
                      '<stop offset="0%" style="stop-color:' + color + ';stop-opacity:1" />' +
                      '<stop offset="100%" style="stop-color:' + color + 'cc;stop-opacity:1" />' +
                      '</linearGradient></defs>' +
                      '<path d="M12 0C5.4 0 0 5.4 0 12c0 9 12 24 12 24s12-15 12-24C24 5.4 18.6 0 12 0z" fill="url(#g' + ip.ip_address.replace(/\./g,'') + ')" stroke="#fff" stroke-width="1.5"/>' +
                      '<circle cx="12" cy="12" r="4" fill="#fff" opacity="0.9"/>' +
                      '<text x="12" y="28" text-anchor="middle" fill="' + color + '" font-size="7" font-weight="bold">' + ip.visit_count + '</text>' +
                      '</svg></div>',
                iconSize: [size, size * 1.4],
                iconAnchor: [size / 2, size * 1.4],
                popupAnchor: [0, -size * 1.4]
            });
            
            var marker = L.marker([gcj.lat, gcj.lng], { icon: icon }).addTo(map);
            
            marker.bindPopup(
                '<div style="min-width:200px;">' +
                '<h6 style="margin:0 0 8px 0;border-bottom:1px solid #ddd;padding-bottom:5px;">' +
                '<i class="fas fa-network-wired"></i> ' + ip.ip_address + '</h6>' +
                '<p style="margin:5px 0;"><strong>国家:</strong> ' + (ip.country || '未知') + '</p>' +
                '<p style="margin:5px 0;"><strong>城市:</strong> ' + (ip.city || '未知') + '</p>' +
                '<p style="margin:5px 0;"><strong>访问次数:</strong> <span style="background:#007bff;color:#fff;padding:2px 8px;border-radius:10px;">' + ip.visit_count + '</span></p>' +
                '<p style="margin:5px 0;"><strong>最后访问:</strong><br><small>' + ip.last_visit + '</small></p>' +
                '</div>'
            );
            markers.push(marker);
        }
    });
    
    if (markers.length > 0) {
        var group = new L.featureGroup(markers);
        map.fitBounds(group.getBounds().pad(0.1));
    }
}

function getColorByCount(count) {
    if (count > 100) return '#ea5545';   // 珊瑚红
    if (count > 50) return '#f46d43';    // 橙红
    if (count > 20) return '#fdae61';    // 橙黄
    if (count > 10) return '#66c2a5';    // 青绿
    return '#5e81f4';                    // 清蓝
}

// ========== 刷新IP位置 ==========
function refreshIpLocations() {
    if (!confirm('每次刷新将处理10个IP的位置信息，确定继续吗？')) {
        return;
    }
    
    var hours = parseInt(_ipPanel.getAttribute('data-hours')) || 24;
    var btn = event.target.closest('button');
    var originalText = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 获取中...';
    
    var fd = new FormData();
    fd.append('hours', hours);
    fd.append('limit', 10);
    
    fetch(ipUrl('data-refresh-url'), {
        method: 'POST',
        body: fd
    })
    .then(function(r) { return r.json(); })
    .then(function(data) {
        if (data.success) {
            alert(data.message);
            location.reload();
        } else {
            alert('失败: ' + data.message);
        }
    })
    .catch(function(err) { alert('请求失败: ' + err); })
    .finally(function() {
        btn.disabled = false;
        btn.innerHTML = originalText;
    });
}

// ========== 手动测试IP位置 ==========
function testIpLocation() {
    var ip = document.getElementById('testIpInput').value.trim();
    if (!ip) { alert('请输入IP地址'); return; }
    if (/^\d+\.\d+\.\d+\.\d+$/.test(ip) === false && /^[0-9a-fA-F:]+$/.test(ip) === false) {
        alert('请输入正确的IP地址格式'); return;
    }
    
    var btn = document.querySelector('#testIpInput + button');
    btn.disabled = true;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 查询中...';
    
    var fd = new FormData();
    fd.append('ip', ip);
    
    fetch(ipUrl('data-test-url'), { method: 'POST', body: fd })
    .then(function(r) { return r.json(); })
    .then(function(data) {
        if (!data.success) {
            alert(data.message || '查询失败');
            return;
        }
        var loc = data.data;
        var wgsLat = parseFloat(loc.latitude);
        var wgsLng = parseFloat(loc.longitude);
        var gcj = wgs84ToGcj02(wgsLat, wgsLng);
        
        // 跳转到该位置
        map.setView([gcj.lat, gcj.lng], 10);
        
        // 添加测试标记（金色边框区分）
        var testMarker = L.marker([gcj.lat, gcj.lng], {
            icon: L.divIcon({
                className: '',
                html: '<div style="position:relative;width:36px;height:50px;">' +
                      '<svg viewBox="0 0 24 36" width="36" height="50">' +
                      '<path d="M12 0C5.4 0 0 5.4 0 12c0 9 12 24 12 24s12-15 12-24C24 5.4 18.6 0 12 0z" fill="#ff6600" stroke="#fff" stroke-width="2"/>' +
                      '<circle cx="12" cy="12" r="4.5" fill="#fff"/>' +
                      '<text x="12" y="28" text-anchor="middle" fill="#ff6600" font-size="8" font-weight="bold">测试</text>' +
                      '</svg></div>',
                iconSize: [36, 50],
                iconAnchor: [18, 50],
                popupAnchor: [0, -50]
            })
        }).addTo(map);
        
        testMarker.bindPopup(
            '<div style="min-width:200px;border-left:4px solid #ff6600;padding:8px;">' +
            '<h6 style="margin:0 0 8px 0;border-bottom:1px solid #ddd;padding-bottom:5px;"><i class="fas fa-search"></i> IP测试结果</h6>' +
            '<p><strong>IP:</strong> ' + loc.ip_address + '</p>' +
            '<p><strong>国家:</strong> ' + (loc.country || '未知') + '</p>' +
            '<p><strong>城市:</strong> ' + (loc.city || '未知') + '</p>' +
            '<p><strong>坐标:</strong> ' + wgsLat.toFixed(4) + ', ' + wgsLng.toFixed(4) + '</p>' +
            '</div>'
        ).openPopup();
        markers.push(testMarker);
    })
    .catch(function(err) { alert('请求失败: ' + err); })
    .finally(function() {
        btn.disabled = false;
        btn.innerHTML = '<i class="fas fa-map-marker-alt"></i> 测试';
    });
}

// ========== 封禁/解封 ==========
function showBlockModal(ipAddress) {
    document.getElementById('blockIpAddress').value = ipAddress;
    var modal = new bootstrap.Modal(document.getElementById('blockIpModal'));
    modal.show();
}

function submitBlockIp() {
    var fd = new FormData(document.getElementById('blockIpForm'));
    fetch(ipUrl('data-block-url'), { method: 'POST', body: fd })
    .then(function(r) { return r.json(); })
    .then(function(data) {
        if (data.success) { alert('封禁成功！'); location.reload(); }
        else { alert('封禁失败：' + data.message); }
    })
    .catch(function(err) { alert('请求失败：' + err); });
}

function unblockIp(ipAddress) {
    if (!confirm('确定要解封IP ' + ipAddress + ' 吗？')) return;
    var fd = new FormData();
    fd.append('ip_address', ipAddress);
    fetch(ipUrl('data-unblock-url'), { method: 'POST', body: fd })
    .then(function(r) { return r.json(); })
    .then(function(data) {
        if (data.success) { alert('解封成功！'); location.reload(); }
        else { alert('解封失败：' + data.message); }
    })
    .catch(function(err) { alert('请求失败：' + err); });
}

// ========== 趋势图 ==========
var trendChart = null;

function initTrendChart() {
    if (trendChart) { trendChart.destroy(); trendChart = null; }
    
    var canvas = document.getElementById('timelineChart');
    if (!canvas) return;
    
    if (typeof Chart === 'undefined') {
        console.error('Chart.js 未加载');
        return;
    }
    
    /* timelineDataRaw set from #ip-timeline-data above */
    var timelineData = timelineDataRaw || [];
    
    console.log('趋势图数据:', timelineData);
    
    if (!timelineData || timelineData.length === 0) {
        var parent = canvas.parentElement;
        if (parent) {
            parent.textContent = '';
            var emptyDiv = document.createElement('div');
            emptyDiv.style.cssText = 'display:flex;flex-direction:column;align-items:center;justify-content:center;height:300px;color:rgba(255,255,255,0.5);';
            var emptyIcon = document.createElement('i');
            emptyIcon.className = 'fas fa-chart-line fa-4x mb-3';
            emptyIcon.style.opacity = '0.5';
            var emptyH5 = document.createElement('h5');
            emptyH5.textContent = '暂无访问趋势数据';
            var emptyP = document.createElement('p');
            emptyP.textContent = '随着用户访问，趋势图将自动更新';
            emptyDiv.appendChild(emptyIcon);
            emptyDiv.appendChild(emptyH5);
            emptyDiv.appendChild(emptyP);
            parent.appendChild(emptyDiv);
        }
        return;
    }
    
    var labels = timelineData.map(function(item) { 
        // 修复可能的格式字符串（如果 time_slot 包含 % 说明是格式字符串）
        var t = item.time_slot;
        if (t && t.indexOf('%') >= 0) {
            return '数据';
        }
        return t; 
    });
    var requestCounts = timelineData.map(function(item) { return item.request_count; });
    var uniqueIps = timelineData.map(function(item) { return item.unique_ips; });
    
    trendChart = new Chart(canvas.getContext('2d'), {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: '访问次数',
                data: requestCounts,
                borderColor: '#4ecdc4',
                backgroundColor: 'rgba(78, 205, 196, 0.15)',
                tension: 0.4,
                fill: true,
                pointRadius: 4,
                pointHoverRadius: 6
            }, {
                label: '独立IP数',
                data: uniqueIps,
                borderColor: '#ff6b9d',
                backgroundColor: 'rgba(255, 107, 157, 0.15)',
                tension: 0.4,
                fill: true,
                pointRadius: 4,
                pointHoverRadius: 6
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { mode: 'index', intersect: false },
            plugins: {
                legend: {
                    labels: { color: 'rgba(255,255,255,0.8)', usePointStyle: true, padding: 15 }
                },
                tooltip: {
                    backgroundColor: 'rgba(0,0,0,0.8)',
                    titleColor: '#fff',
                    bodyColor: '#fff'
                }
            },
            scales: {
                x: {
                    ticks: { color: 'rgba(255,255,255,0.6)', maxRotation: 30 },
                    grid: { color: 'rgba(255,255,255,0.05)' }
                },
                y: {
                    beginAtZero: true,
                    ticks: { color: 'rgba(255,255,255,0.6)' },
                    grid: { color: 'rgba(255,255,255,0.05)' }
                }
            }
        }
    });
}
