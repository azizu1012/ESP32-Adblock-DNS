"""HTTP web server: dashboard, stats API, config, upload.

Routes:
  GET  /             — Dashboard (dark theme, live stats)
  GET  /api/stats    — JSON stats endpoint
  POST /api/upload   — Upload blocked.bin mới (stream ghi vào flash)
  POST /api/config/wifi — Lưu WiFi config & reboot
  POST /api/config/reset — Xoá config & reboot
  POST /api/config/dhcp   — Chuyển sang DHCP & reboot
  GET  /setup        — WiFi setup page
"""
import socket
import json
import time
from stats import Stats


DASHBOARD_HTML = """<!DOCTYPE html>
<html data-theme="dark">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<script src="https://cdn.tailwindcss.com"></script>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<script src="https://unpkg.com/lucide@latest"></script>
<title>ESP32 AdBlocker</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#080c18;color:#e2e8f0;font-family:system-ui,-apple-system,sans-serif;min-height:100vh}
.glass-nav{background:rgba(8,12,24,0.45);backdrop-filter:blur(20px);-webkit-backdrop-filter:blur(20px);border-bottom:1px solid rgba(255,255,255,0.05);position:sticky;top:0;z-index:50;padding:12px 24px;display:flex;align-items:center;justify-content:space-between}
.glass-card{background:rgba(13,18,30,0.4);backdrop-filter:blur(16px);-webkit-backdrop-filter:blur(16px);border:1px solid rgba(255,255,255,0.06);border-radius:16px;padding:20px;transition:all 0.3s ease}
.glass-card:hover{transform:translateY(-2px);border-color:rgba(99,102,241,0.3)}
@keyframes fadeInUp{from{opacity:0;transform:translateY(16px)}to{opacity:1;transform:translateY(0)}}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:0.5}}
@keyframes countUp{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:translateY(0)}}
.animate-in{animation:fadeInUp 0.5s ease forwards;opacity:0}
.cascade-1{animation-delay:0.1s}.cascade-2{animation-delay:0.18s}.cascade-3{animation-delay:0.26s}.cascade-4{animation-delay:0.34s}
.cascade-5{animation-delay:0.42s}.cascade-6{animation-delay:0.50s}
.status-dot{width:10px;height:10px;border-radius:50%;background:#22c55e;display:inline-block;animation:pulse 2s infinite;box-shadow:0 0 8px rgba(34,197,94,0.5)}
.live-badge{font-size:11px;font-weight:600;color:#22c55e;letter-spacing:1px}
.kpi-icon{width:40px;height:40px;border-radius:12px;display:flex;align-items:center;justify-content:center;font-size:18px}
.kpi-value{font-size:28px;font-weight:700;letter-spacing:-0.5px;animation:countUp 0.6s ease forwards}
.kpi-label{font-size:13px;color:#94a3b8;margin-top:2px}
::-webkit-scrollbar{width:4px}
::-webkit-scrollbar-track{background:transparent}
::-webkit-scrollbar-thumb{background:rgba(99,102,241,0.3);border-radius:2px}
.chart-container{position:relative;height:200px;width:100%}
</style>
</head>
<body>

<nav class="glass-nav">
<div style="display:flex;align-items:center;gap:12px">
<span class="status-dot"></span>
<span style="font-weight:700;font-size:18px;color:#f1f5f9">ESP32 AdBlocker</span>
</div>
<div style="display:flex;align-items:center;gap:16px">
<span class="live-badge" id="liveBadge">LIVE</span>
<span id="uptimeDisplay" style="font-size:13px;color:#64748b;font-family:monospace">--</span>
<a href="/setup" style="font-size:13px;color:#818cf8;text-decoration:none;font-weight:500">⚙ Setup</a>
</div>
</nav>

<main style="max-width:1200px;margin:0 auto;padding:20px 16px">

<!-- KPI Cards -->
<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:16px;margin-bottom:20px">
<div class="glass-card animate-in cascade-1">
<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px">
<span class="kpi-icon" style="background:rgba(99,102,241,0.15);color:#818cf8" data-lucide="activity"></span>
</div>
<div class="kpi-value" id="totalCount">0</div>
<div class="kpi-label">Total Queries</div>
</div>

<div class="glass-card animate-in cascade-2">
<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px">
<span class="kpi-icon" style="background:rgba(239,68,68,0.15);color:#ef4444" data-lucide="shield-off"></span>
</div>
<div class="kpi-value" id="blockedCount" style="color:#ef4444">0</div>
<div class="kpi-label">Blocked</div>
</div>

<div class="glass-card animate-in cascade-3">
<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px">
<span class="kpi-icon" style="background:rgba(34,197,94,0.15);color:#22c55e" data-lucide="shield-check"></span>
</div>
<div class="kpi-value" id="allowedCount" style="color:#22c55e">0</div>
<div class="kpi-label">Allowed</div>
</div>

<div class="glass-card animate-in cascade-4">
<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px">
<span class="kpi-icon" style="background:rgba(245,158,11,0.15);color:#f59e0b" data-lucide="pie-chart"></span>
</div>
<div class="kpi-value" id="ratioCount" style="color:#f59e0b">0%</div>
<div class="kpi-label">Block Ratio</div>
</div>

<div class="glass-card animate-in cascade-5">
<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px">
<span class="kpi-icon" style="background:rgba(99,102,241,0.15);color:#818cf8" data-lucide="list"></span>
</div>
<div class="kpi-value" id="entriesCount" style="font-size:22px">0</div>
<div class="kpi-label">Blocked Domains</div>
</div>
</div>

<!-- Charts + System -->
<div style="display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-bottom:20px">
<div class="glass-card animate-in cascade-6">
<h3 style="font-size:14px;font-weight:600;color:#94a3b8;margin-bottom:12px;text-transform:uppercase;letter-spacing:0.5px">Block vs Allowed</h3>
<div class="chart-container">
<canvas id="donutChart"></canvas>
</div>
</div>

 <div class="glass-card"> <h3 style="font-size:14px;font-weight:600;color:#94a3b8;margin-bottom:16px;text-transform:uppercase;letter-spacing:0.5px">System Info</h3>
 <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:10px">
 <div style="background:rgba(255,255,255,0.03);border-radius:10px;padding:10px">
 <div style="display:flex;align-items:center;gap:6px;margin-bottom:4px">
 <span data-lucide="memory-stick" style="width:13px;height:13px;color:#818cf8"></span>
 <span style="font-size:11px;color:#94a3b8">RAM (GC heap)</span>
 </div>
  <div style="font-size:14px;font-weight:700;font-family:monospace" id="ramValue">--</div>
  <div style="font-size:10px;color:#64748b;margin-top:1px"><span id="ramFree">--</span> free (<span id="ramPct">0</span>%)</div>
  <div style="width:100%;height:4px;background:rgba(255,255,255,0.06);border-radius:2px;margin-top:4px"><div style="height:100%;border-radius:2px;background:#818cf8;transition:width 0.5s" id="ramBar"></div></div>
  </div>
  <div style="background:rgba(255,255,255,0.03);border-radius:10px;padding:10px">
  <div style="display:flex;align-items:center;gap:6px;margin-bottom:4px">
  <span data-lucide="hard-drive" style="width:13px;height:13px;color:#22c55e"></span>
  <span style="font-size:11px;color:#94a3b8">Flash (FS)</span>
  </div>
  <div style="font-size:14px;font-weight:700;font-family:monospace" id="flashValue">--</div>
  <div style="font-size:10px;color:#64748b;margin-top:1px"><span id="flashFree">--</span> free (chip: <span id="flashChip">--</span>, <span id="flashPct">0</span>%)</div>
  <div style="width:100%;height:4px;background:rgba(255,255,255,0.06);border-radius:2px;margin-top:4px"><div style="height:100%;border-radius:2px;background:#22c55e;transition:width 0.5s" id="flashBar"></div></div>
 </div>
 <div style="background:rgba(255,255,255,0.03);border-radius:10px;padding:10px">
 <div style="display:flex;align-items:center;gap:6px;margin-bottom:4px">
 <span data-lucide="cpu" style="width:13px;height:13px;color:#f59e0b"></span>
 <span style="font-size:11px;color:#94a3b8">CPU</span>
 </div>
 <div style="font-size:14px;font-weight:700;font-family:monospace" id="cpuValue">-- MHz</div>
 <div style="font-size:10px;color:#64748b;margin-top:1px" id="coreValue">-- cores</div>
 </div>
 <div style="background:rgba(255,255,255,0.03);border-radius:10px;padding:10px">
 <div style="display:flex;align-items:center;gap:6px;margin-bottom:4px">
 <span data-lucide="thermometer" style="width:13px;height:13px;color:#f59e0b"></span>
 <span style="font-size:11px;color:#94a3b8">CPU Temp</span>
 </div>
 <div style="font-size:16px;font-weight:700;font-family:monospace" id="tempValue">--</div>
 </div>
 <div style="background:rgba(255,255,255,0.03);border-radius:10px;padding:10px">
 <div style="display:flex;align-items:center;gap:6px;margin-bottom:4px">
 <span data-lucide="clock" style="width:13px;height:13px;color:#22c55e"></span>
 <span style="font-size:11px;color:#94a3b8">Uptime</span>
 </div>
 <div style="font-size:16px;font-weight:700;font-family:monospace" id="uptimeValue">--</div>
 </div>
 <div style="background:rgba(255,255,255,0.03);border-radius:10px;padding:10px">
 <div style="display:flex;align-items:center;gap:6px;margin-bottom:4px">
 <span data-lucide="wifi" style="width:13px;height:13px;color:#22c55e"></span>
 <span style="font-size:11px;color:#94a3b8">IP Address</span>
 </div>
 <div style="font-size:14px;font-weight:700;font-family:monospace;word-break:break-all" id="ipValue">--</div>
 </div>
  <div style="background:rgba(255,255,255,0.03);border-radius:10px;padding:10px">
  <div style="display:flex;align-items:center;gap:6px;margin-bottom:4px">
  <span data-lucide="server" style="width:13px;height:13px;color:#818cf8"></span>
  <span style="font-size:11px;color:#94a3b8">DNS Upstream</span>
  </div>
  <div style="font-size:13px;font-weight:700;font-family:monospace;word-break:break-all" id="upstreamValue">--</div>
  </div>
  <div style="background:rgba(255,255,255,0.03);border-radius:10px;padding:10px">
  <div style="display:flex;align-items:center;gap:6px;margin-bottom:4px">
  <span data-lucide="zap" style="width:13px;height:13px;color:#f59e0b"></span>
  <span style="font-size:11px;color:#94a3b8">DNS Latency</span>
  </div>
  <div style="font-size:16px;font-weight:700;font-family:monospace" id="latencyValue">--</div>
  </div>
  </div> </div>
 </div>
 </div>
</div>

<!-- Top Blocked -->
<div style="display:grid;grid-template-columns:1fr 1fr;gap:20px">
<div class="glass-card animate-in cascade-6">
<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px">
<h3 style="font-size:14px;font-weight:600;color:#94a3b8;text-transform:uppercase;letter-spacing:0.5px">Recent Queries</h3>
<span style="font-size:12px;color:#64748b" id="liveLabel">--</span>
</div>
<div id="recentList" style="max-height:380px;overflow-y:auto;padding-right:4px">
<div style="text-align:center;padding:24px 0;color:#64748b;font-size:14px">Waiting for queries...</div>
</div>
</div>

<div class="glass-card animate-in cascade-6">
<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px">
<h3 style="font-size:14px;font-weight:600;color:#94a3b8;text-transform:uppercase;letter-spacing:0.5px">Top Blocked</h3>
<span id="totalLabel" style="font-size:12px;color:#64748b">0 blocked</span>
</div>
<div id="topList">
<div style="text-align:center;padding:24px 0;color:#64748b;font-size:14px">No domains blocked yet</div>
</div>
</div>
</div>

</main>

<script>
tailwind.config={theme:{extend:{colors:{accent:'#6366f1'}}}}

let donutChart=null

function formatNum(n){
  if(n>=1000000)return(n/1000000).toFixed(1)+'M'
  if(n>=1000)return(n/1000).toFixed(1)+'K'
  return n.toString()
}

function updateDashboard(data){
  document.getElementById('totalCount').textContent=formatNum(data.total)
  document.getElementById('blockedCount').textContent=formatNum(data.blocked)
  document.getElementById('allowedCount').textContent=formatNum(data.allowed)
  document.getElementById('ratioCount').textContent=data.ratio+'%'
  document.getElementById('entriesCount').textContent=formatNum(data.blocklist_entries||0)
  document.getElementById('totalLabel').textContent=data.blocked+' blocked'
  document.getElementById('liveLabel').textContent=data.total+' queries'

  // Recent queries
  const recentEl=document.getElementById('recentList')
  if(!data.recent||data.recent.length===0){
    recentEl.innerHTML='<div style="text-align:center;padding:24px 0;color:#64748b;font-size:14px">Waiting for queries...</div>'
  }else{
    recentEl.innerHTML=data.recent.slice(-30).reverse().map(function(r){
      const domain=r[0],blocked=r[1],cat=r[2],age=r[3],layer=r[4],ip=r[5]
      const timeStr=age<3?'now':age<60?age+'s':Math.floor(age/60)+'m'
      const catBadge=blocked&&cat?' <span style="font-size:9px;padding:1px 4px;border-radius:3px;background:rgba(99,102,241,0.15);color:#818cf8;margin-left:2px">'+cat+'</span>':''
      const layerBadge=blocked&&layer?' <span style="font-size:9px;padding:1px 4px;border-radius:3px;background:rgba(245,158,11,0.15);color:#f59e0b;margin-left:2px">'+layer+'</span>':''
      const ipStr=ip?'<span style="color:#64748b;font-size:11px;font-family:monospace;margin-right:4px">['+ip+']</span>':''
      return '<div style="display:flex;align-items:center;gap:6px;padding:5px 0;border-bottom:1px solid rgba(255,255,255,0.04);font-size:13px"><span style="font-size:10px;padding:1px 6px;border-radius:4px;font-weight:600;'+(blocked?'background:rgba(239,68,68,0.15);color:#ef4444':'background:rgba(34,197,94,0.15);color:#22c55e')+'">'+(blocked?'BLOCK':'PASS')+'</span>'+catBadge+layerBadge+'<span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">'+ipStr+domain+'</span><span style="color:#64748b;font-size:11px">'+timeStr+'</span></div>'
    }).join('')
  }

  const u=data.uptime
  const h=Math.floor(u/3600)
  const m=Math.floor((u%3600)/60)
  const s=u%60
  const uptimeStr=h+'h '+m+'m '+s+'s'
  document.getElementById('uptimeDisplay').textContent=uptimeStr
  document.getElementById('uptimeValue').textContent=h+'h '+m+'m'
  document.getElementById('upstreamValue').textContent=data.upstream||'--'
  document.getElementById('latencyValue').textContent=(data.upstream_rtt!==undefined&&data.upstream_rtt<999999)?data.upstream_rtt+' ms':'--'

  const totalKB=Math.round((data.total_ram||0)/1024)
  const usedKB=Math.round((data.alloc_ram||0)/1024)
  const freeKB=Math.round((data.free_ram||0)/1024)
  const pct=totalKB?Math.round(usedKB/totalKB*100):0
  document.getElementById('ramValue').textContent=usedKB+'KB / '+totalKB+'KB'
  document.getElementById('ramFree').textContent=freeKB+'KB'
  document.getElementById('ramPct').textContent=pct
  document.getElementById('ramBar').style.width=Math.min(pct,100)+'%'

  const ft=Math.round((data.flash_total||0)/1024)
  const ff=Math.round((data.flash_free||0)/1024)
  const fc=Math.round((data.flash_chip||0)/1024)
  const fu=ft-ff
  const fp=ft?Math.round(fu/ft*100):0
  document.getElementById('flashValue').textContent=fu+'KB / '+ft+'KB'
  document.getElementById('flashFree').textContent=ff+'KB'
  document.getElementById('flashChip').textContent=fc+'KB'
  document.getElementById('flashPct').textContent=fp
  document.getElementById('flashBar').style.width=Math.min(fp,100)+'%'

  document.getElementById('cpuValue').textContent=(data.cpu_freq||240)+' MHz'
  document.getElementById('coreValue').textContent=(data.core_count||2)+' cores'

  document.getElementById('ipValue').textContent=data.ip||'--'
  if(data.cpu_temp&&data.cpu_temp<100){document.getElementById('tempValue').textContent=data.cpu_temp+'°C'}else{document.getElementById('tempValue').textContent='--'}

  // Donut chart
  try{
    const hasData = (data.blocked > 0 || data.allowed > 0);
    const chartData = hasData ? [data.blocked, data.allowed] : [0, 1];
    const chartColors = hasData ? ['rgba(239,68,68,0.8)','rgba(34,197,94,0.8)'] : ['rgba(239,68,68,0.1)','rgba(255,255,255,0.05)'];
    const chartBorders = hasData ? ['#ef4444','#22c55e'] : ['rgba(259,68,68,0.1)','rgba(255,255,255,0.1)'];

    if(typeof Chart !== 'undefined'){
      if(!donutChart){
        const ctx=document.getElementById('donutChart').getContext('2d')
        donutChart=new Chart(ctx,{
          type:'doughnut',
          data:{
            labels:['Blocked','Allowed'],
            datasets:[{
              data:chartData,
              backgroundColor:chartColors,
              borderColor:chartBorders,
              borderWidth:2,
              hoverOffset:8
            }]
          },
          options:{
            responsive:true,
            maintainAspectRatio:false,
            cutout:'70%',
            plugins:{
              legend:{
                position:'bottom',
                labels:{color:'#94a3b8',padding:12,usePointStyle:true,font:{size:12}}
              }
            },
            animation:{animateRotate:true,duration:800}
          }
        })
      }else{
        donutChart.data.datasets[0].data=chartData
        donutChart.data.datasets[0].backgroundColor=chartColors
        donutChart.data.datasets[0].borderColor=chartBorders
        donutChart.update()
      }
    }
  }catch(e){console.error(e)}

  // Top blocked
  const topEl=document.getElementById('topList')
  if(!data.top||data.top.length===0){
    topEl.innerHTML='<div style="text-align:center;padding:24px 0;color:#64748b;font-size:14px">No domains blocked yet</div>'
  }else{
    const maxC=data.top[0].c
    topEl.innerHTML=data.top.map(function(item,i){
      const pct=Math.round(item.c/maxC*100)
      const catBadge=item.g?' <span style="font-size:9px;padding:1px 4px;border-radius:3px;background:rgba(99,102,241,0.12);color:#818cf8">'+item.g+'</span>':''
      return'<div style="display:flex;align-items:center;gap:8px;padding:6px 0"><span style="font-size:12px;color:#64748b;min-width:20px">'+(i+1)+'.</span><div style="flex:1;min-width:0"><div style="font-size:13px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">'+item.d+catBadge+'</div><div style="width:100%;height:3px;background:rgba(255,255,255,0.06);border-radius:2px;margin-top:3px"><div style="height:100%;border-radius:2px;background:#ef4444;width:'+pct+'%"></div></div></div><span style="font-size:12px;color:#94a3b8;font-weight:600;min-width:32px;text-align:right">'+item.c+'</span></div>'
    }).join('')
  }
}

async function fetchStats(){
  try{
    const r=await fetch('/api/stats')
    const d=await r.json()
    updateDashboard(d)
  }catch(e){}
}

fetchStats()
setInterval(fetchStats,3000)
lucide.createIcons()
</script>
</body>
</html>"""


class WebServer:
    def __init__(self, stats, ip="0.0.0.0", port=80):
        """Khởi tạo web server với stats và địa chỉ IP."""
        self.stats = stats
        self.ip = ip
        self.port = port
        self.sock = None

    def start(self):
        """Mở socket TCP, bind, listen với timeout 1s."""
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind((self.ip, self.port))
        self.sock.listen(2)
        self.sock.settimeout(1.0)
        print(f"Web server on port {self.port}")

    def serve(self, wifi_manager=None):
        """Vòng lặp chính: chấp nhận kết nối, xử lý request, đóng."""
        self.start()
        while True:
            try:
                conn, addr = self.sock.accept()
            except OSError:
                continue
            try:
                conn.settimeout(2.0)
                self._handle(conn, wifi_manager)
            except Exception as e:
                print("HTTP serve error:", e)
            finally:
                try:
                    conn.close()
                except:
                    pass

    def _handle(self, conn, wifi_manager):
        """Parse HTTP request header và điều hướng đến handler phù hợp."""
        try:
            buf = conn.recv(1024)
            if not buf:
                return
            while b"\r\n\r\n" not in buf:
                chunk = conn.recv(256)
                if not chunk:
                    break
                buf += chunk

            idx = buf.find(b"\r\n\r\n")
            header_part = buf[:idx].decode("utf-8")
            path = header_part.split(" ")[1] if " " in header_part else "/"
            method = header_part.split(" ")[0] if " " in header_part else "GET"

            if path == "/api/upload":
                conn.settimeout(120.0)
                self._handle_upload(conn, buf)
            elif method == "POST":
                self._handle_post(conn, buf, path, wifi_manager)
            elif path == "/api/stats":
                self._send_json(conn, self._build_stats(wifi_manager))
            elif path.startswith("/api/"):
                self._send_json(conn, {"error": "not found"})
            elif path == "/setup":
                self._send_html(conn, self._config_html(wifi_manager))
            else:
                self._send_html(conn, DASHBOARD_HTML)
        except Exception as e:
            print("Handle error:", e)

    def _handle_post(self, conn, data, path, wifi_manager):
        """Xử lý POST request: config wifi, reboot, reset, dhcp."""
        request = data.decode("utf-8")
        if path == "/api/config/wifi":
            body = self._parse_body(request)
            ssid = body.get("ssid", "")
            password = body.get("password", "")
            if ssid:
                from config import ConfigManager
                cfg = ConfigManager.load()
                cfg["ssid"] = ssid
                cfg["password"] = password
                if body.get("noip_user"):
                    cfg["noip_user"] = body["noip_user"]
                if body.get("noip_pass"):
                    cfg["noip_pass"] = body["noip_pass"]
                if body.get("noip_host"):
                    cfg["noip_host"] = body["noip_host"]
                ConfigManager.save(cfg)
                self._send_json(conn, {"ok": True, "message": "Saved. Rebooting..."})
                import machine
                time.sleep(1)
                machine.reset()
                return
            self._send_json(conn, {"ok": False, "error": "ssid required"})
        elif path == "/api/reboot":
            self._send_json(conn, {"ok": True, "message": "Rebooting..."})
            import machine
            time.sleep(0.5)
            machine.reset()
        elif path == "/api/config/reset":
            from config import ConfigManager
            ConfigManager.delete()
            self._send_json(conn, {"ok": True, "message": "Reset. Rebooting..."})
            import machine
            time.sleep(1)
            machine.reset()
        elif path == "/api/config/dhcp":
            from config import ConfigManager
            cfg = ConfigManager.load()
            cfg["ip"] = ""
            cfg["gateway"] = ""
            ConfigManager.save(cfg)
            self._send_json(conn, {"ok": True, "message": "DHCP mode. Rebooting..."})
            import machine
            time.sleep(1)
            machine.reset()
        else:
            self._send_json(conn, {"ok": False, "error": "unknown endpoint"})
    def _handle_upload(self, conn, data):
        """Nhận file blocked.bin mới qua HTTP, ghi trực tiếp vào flash (stream)."""
        try:
            header_end = data.find(b"\r\n\r\n")
            if header_end == -1:
                self._send_json(conn, {"ok": False, "error": "bad request"})
                return

            header_part = data[:header_end].decode("utf-8")
            cl = 0
            for line in header_part.split("\r\n"):
                if line.lower().startswith("content-length:"):
                    cl = int(line.split(":")[1].strip())
                    break

            if cl < 1024:
                self._send_json(conn, {"ok": False, "error": "file too small"})
                return

            body_start = header_end + 4
            written = len(data) - body_start

            import machine
            with open("blocked.bin", "wb") as f:
                f.write(data[body_start:])
                while written < cl:
                    remaining = cl - written
                    chunk = conn.recv(min(1024, remaining))
                    if not chunk:
                        break
                    f.write(chunk)
                    written += len(chunk)
                    if written % 16384 == 0:
                        f.flush()
                        machine.idle()

            self._send_json(conn, {"ok": True, "message": "Upload OK (%d bytes)" % cl})
        except Exception as e:
            self._send_json(conn, {"ok": False, "error": str(e)})

    @staticmethod
    def _parse_body(request):
        """Giải nén body JSON từ HTTP request."""
        parts = request.split("\r\n\r\n", 1)
        if len(parts) < 2:
            return {}
        try:
            return json.loads(parts[1])
        except:
            return {}

    def _build_stats(self, wifi_manager):
        """Xây dựng dict stats JSON, thêm cpu_temp và IP."""
        if self.stats is None:
            d = {"total": 0, "blocked": 0, "allowed": 0, "ratio": 0,
                 "uptime": 0, "free_ram": 0, "alloc_ram": 0, "total_ram": 0,
                 "last_blocked": "", "recent": [], "cpu_temp": None, "ip": "",
                 "top": [], "flash_free": 0, "flash_total": 0, "flash_chip": 0,
                 "blocklist_entries": 0, "cpu_freq": 0, "core_count": 0,
                 "upstream": "1.1.1.1", "upstream_rtt": 0}
            if wifi_manager and wifi_manager.is_connected():
                try:
                    d["ip"] = wifi_manager.ifconfig()[0]
                except:
                    pass
            return d
        d = self.stats.to_dict()
        d["cpu_temp"] = self._get_cpu_temp()
        d["ip"] = ""
        if wifi_manager and wifi_manager.is_connected():
            try:
                d["ip"] = wifi_manager.ifconfig()[0]
            except:
                pass
        return d

    @staticmethod
    def _get_cpu_temp():
        """Đọc nhiệt độ CPU từ cảm biến trong ESP32, trả về °C."""
        try:
            import esp32
            raw = esp32.raw_temperature()
            if raw < 50 or raw > 200:
                return None
            return round((raw - 32) / 1.8, 1)
        except:
            return None

    @staticmethod
    def _send_json(conn, data):
        """Gửi HTTP response dạng JSON."""
        body = json.dumps(data)
        resp = (
            "HTTP/1.1 200 OK\r\n"
            "Content-Type: application/json\r\n"
            "Connection: close\r\n"
            "Access-Control-Allow-Origin: *\r\n"
            f"Content-Length: {len(body)}\r\n"
            "\r\n" + body
        )
        conn.sendall(resp.encode())

    @staticmethod
    def _send_html(conn, html):
        """Gửi HTTP response dạng HTML."""
        resp = (
            "HTTP/1.1 200 OK\r\n"
            "Content-Type: text/html; charset=utf-8\r\n"
            "Connection: close\r\n"
            f"Content-Length: {len(html)}\r\n"
            "\r\n" + html
        )
        conn.sendall(resp.encode())

    @staticmethod
    def _config_html(wifi_manager=None):
        """Tạo HTML trang setup WiFi + No-IP DDNS."""
        ip = ""
        try:
            if wifi_manager and wifi_manager.is_connected():
                ip = wifi_manager.ifconfig()[0] or ""
        except:
            pass
        if ip:
            bg = "rgba(34,197,94,0.1);border-color:rgba(34,197,94,0.2)"
            msg = '<span data-lucide="check-circle" style="width:16px;height:16px;flex-shrink:0;color:#22c55e"></span><span style="color:#22c55e">Connected &mdash; {0}</span>'.format(ip)
        else:
            status = "disconnected"
            bg = "rgba(245,158,11,0.1);border-color:rgba(245,158,11,0.2)"
            msg = '<span data-lucide="alert-triangle" style="width:16px;height:16px;flex-shrink:0;color:#fbbf24"></span><span style="color:#fbbf24">Not connected. Enter your Wi-Fi details below.</span>'
        return """<!DOCTYPE html>
<html data-theme="dark">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<script src="https://cdn.tailwindcss.com"></script>
<script src="https://unpkg.com/lucide@latest"></script>
<title>ESP32 Setup</title>
<style>
body{background:#080c18;color:#e2e8f0;font-family:system-ui,-apple-system,sans-serif;min-height:100vh;display:flex;align-items:center;justify-content:center;padding:16px}
.glass-card{background:rgba(13,18,30,0.4);backdrop-filter:blur(16px);-webkit-backdrop-filter:blur(16px);border:1px solid rgba(255,255,255,0.06);border-radius:16px;padding:32px;width:100%;max-width:420px}
input{width:100%;padding:10px 14px;margin:6px 0 14px;background:rgba(255,255,255,0.05);border:1px solid rgba(255,255,255,0.1);border-radius:10px;color:#e2e8f0;font-size:14px;outline:none;transition:border-color 0.2s}
input:focus{border-color:#6366f1}
input::placeholder{color:#475569}
button{width:100%;padding:12px;background:#6366f1;color:white;border:none;border-radius:10px;font-size:15px;font-weight:600;cursor:pointer;transition:all 0.2s}
button:hover{background:#4f46e5;transform:translateY(-1px)}
label{font-size:13px;color:#94a3b8;font-weight:500}
h2{font-size:22px;font-weight:700;margin-bottom:4px}
p{color:#64748b;font-size:14px;margin-bottom:24px}
.status{display:flex;align-items:center;gap:10px;margin-bottom:24px;padding:12px;background:rgba(245,158,11,0.1);border:1px solid rgba(245,158,11,0.2);border-radius:10px;color:#fbbf24;font-size:13px}
hr{border:none;border-top:1px solid rgba(255,255,255,0.06);margin:20px 0}
small{color:#64748b;font-size:12px}
</style>
</head>
<body>
<div class="glass-card">
<div style="display:flex;align-items:center;gap:10px;margin-bottom:4px">
<span data-lucide="wifi" style="color:#818cf8;width:24px;height:24px"></span>
<h2>ESP32 Setup</h2>
</div>
<p>Configure your Wi-Fi to start blocking ads</p>
<div class="status" style="background:""" + bg + """">
""" + msg + """</div>
<form method="POST" action="/api/config/wifi" id="setupForm">
<label>Wi-Fi SSID</label>
<input type="text" name="ssid" required placeholder="Enter Wi-Fi name">

<label>Wi-Fi Password</label>
<input type="password" name="password" placeholder="Leave blank if open">

<hr>

<div style="font-size:13px;color:#94a3b8;font-weight:500;margin-bottom:8px">Dynamic DNS (optional)</div>
<div style="font-size:12px;color:#64748b;margin-bottom:12px">No-IP tự động cập nhật IP khi mạng đổi. Bỏ qua nếu không dùng.</div>

<label>No-IP Username</label>
<input type="text" name="noip_user" placeholder="Email / Username">

<label>No-IP Password</label>
<input type="password" name="noip_pass" placeholder="Password">

<label>No-IP Hostname</label>
<input type="text" name="noip_host" placeholder="yourhost.ddns.net">

<button type="submit">
<span data-lucide="save" style="width:16px;height:16px;vertical-align:middle;margin-right:6px"></span>
Save & Reboot
</button>
</form>
<div style="margin-top:12px;text-align:center">
<a href="/" style="color:#6366f1;font-size:13px;text-decoration:none">← Back to Dashboard</a>
</div>
</div>
 <script>
 try{lucide.createIcons()}catch(e){}
 document.getElementById('setupForm').addEventListener('submit',async function(e){
 e.preventDefault()
 const btn=this.querySelector('button')
 btn.disabled=true;btn.textContent='Saving...'
 const fd=new FormData(this)
 const data=Object.fromEntries(fd)
 try{
 const r=await fetch('/api/config/wifi',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)})
 const j=await r.json()
 if(j.ok){
 btn.textContent='Rebooting...'
 setTimeout(()=>{window.location.href='/'},2000)
 }else{
 alert('Error: '+j.error);btn.disabled=false;btn.innerHTML='<span data-lucide="save" style="width:16px;height:16px;vertical-align:middle;margin-right:6px"></span> Save & Reboot';try{lucide.createIcons()}catch(e){}
 }
 }catch(e){alert('Failed: '+e.message);btn.disabled=false;btn.innerHTML='<span data-lucide="save" style="width:16px;height:16px;vertical-align:middle;margin-right:6px"></span> Save & Reboot';try{lucide.createIcons()}catch(e){}}
 })
 </script>
</body>
</html>"""

    @staticmethod
    def _redirect(conn, path="/"):
        """Gửi HTTP redirect 302."""
        body = f"<html><body><script>window.location='{path}'</script></body></html>"
        resp = (
            "HTTP/1.1 302 Found\r\n"
            f"Location: {path}\r\n"
            "Content-Type: text/html\r\n"
            "Connection: close\r\n"
            f"Content-Length: {len(body)}\r\n"
            "\r\n" + body
        )
        conn.sendall(resp.encode())
