template = open('/home/maksupplies/eshop2/templates/dashboard/combined_profit_report.html', 'w')
template.write("""{% extends 'dashboard/base.html' %}
{% block page_title %}Combined Profit Report{% endblock %}
{% block content %}
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600&family=Syne:wght@600;800&display=swap" rel="stylesheet">
<style>
:root{--accent:#6366f1;--green:#10b981;--red:#ef4444;--yellow:#f59e0b;--blue:#3b82f6}
.rpt-header{font-family:'Syne',sans-serif;font-size:22px;font-weight:800;color:#0f172a;margin-bottom:4px}
.rpt-sub{color:#64748b;font-size:13px;margin-bottom:20px}
.kpi-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:14px;margin-bottom:22px}
.kpi-card{background:#fff;border-radius:14px;padding:18px 16px;box-shadow:0 1px 6px rgba(0,0,0,.06);border-top:3px solid var(--accent);position:relative;overflow:hidden}
.kpi-card.green{border-top-color:var(--green)}.kpi-card.red{border-top-color:var(--red)}.kpi-card.yellow{border-top-color:var(--yellow)}.kpi-card.blue{border-top-color:var(--blue)}.kpi-card.slate{border-top-color:#94a3b8}
.kpi-label{font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:1.2px;color:#94a3b8;margin-bottom:6px}
.kpi-value{font-family:'JetBrains Mono',monospace;font-size:22px;font-weight:600;color:#0f172a}
.kpi-sub{font-size:11px;color:#64748b;margin-top:3px}
.kpi-icon{position:absolute;right:14px;top:14px;font-size:22px;opacity:.15}
.filter-bar{background:#fff;border-radius:12px;padding:16px 20px;box-shadow:0 1px 4px rgba(0,0,0,.05);margin-bottom:18px;display:flex;flex-wrap:wrap;gap:12px;align-items:flex-end}
.filter-bar label{font-size:11px;font-weight:700;color:#64748b;text-transform:uppercase;letter-spacing:.8px;display:block;margin-bottom:4px}
.filter-bar input,.filter-bar select{border:1.5px solid #e2e8f0;border-radius:8px;padding:6px 10px;font-size:13px;color:#1e293b;background:#f8fafc;outline:none}
.btn-filter{background:var(--accent);color:#fff;border:none;border-radius:8px;padding:8px 18px;font-size:13px;font-weight:600;cursor:pointer}
.btn-clear{background:#f1f5f9;color:#64748b;border:none;border-radius:8px;padding:8px 14px;font-size:13px;cursor:pointer;text-decoration:none}
.src-pill{display:inline-block;padding:2px 9px;border-radius:20px;font-size:11px;font-weight:700}
.src-pill.ebay{background:#fef3c7;color:#92400e}.src-pill.eshop{background:#dbeafe;color:#1e40af}
.chart-card{background:#fff;border-radius:14px;padding:20px;box-shadow:0 1px 6px rgba(0,0,0,.06);margin-bottom:22px}
.chart-title{font-family:'Syne',sans-serif;font-size:14px;font-weight:700;color:#0f172a;margin-bottom:14px}
.tbl-wrap{background:#fff;border-radius:14px;box-shadow:0 1px 6px rgba(0,0,0,.06);overflow:hidden}
.tbl-toolbar{padding:14px 18px;display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid #f1f5f9}
.tbl-toolbar-title{font-family:'Syne',sans-serif;font-size:14px;font-weight:700;color:#0f172a}
.tbl-search{border:1.5px solid #e2e8f0;border-radius:8px;padding:6px 12px;font-size:13px;width:220px;outline:none}
table.rpt{width:100%;border-collapse:collapse;font-size:13px}
table.rpt thead th{background:#0f172a;color:#94a3b8;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.8px;padding:11px 12px;white-space:nowrap;cursor:pointer;user-select:none}
table.rpt thead th:hover{color:#fff}table.rpt thead th.sorted{color:#6366f1}
table.rpt tbody tr{border-bottom:1px solid #f1f5f9;transition:background .1s}
table.rpt tbody tr:hover{background:#f8fafc}
table.rpt tbody td{padding:10px 12px;color:#1e293b;vertical-align:middle}
table.rpt tfoot td{background:#1e293b;color:#e2e8f0;font-weight:700;padding:11px 12px;font-family:'JetBrains Mono',monospace;font-size:12px}
.mono{font-family:'JetBrains Mono',monospace}
.profit-badge{display:inline-block;padding:3px 9px;border-radius:6px;font-size:12px;font-weight:700;font-family:'JetBrains Mono',monospace}
.profit-badge.pos{background:#d1fae5;color:#065f46}.profit-badge.neg{background:#fee2e2;color:#991b1b}.profit-badge.zero{background:#f1f5f9;color:#64748b}
.cost-input{width:80px;border:1.5px solid #e2e8f0;border-radius:6px;padding:3px 6px;font-size:12px;font-family:'JetBrains Mono',monospace;background:#f8fafc;outline:none}
.cost-input:focus{border-color:var(--accent);background:#fff}
.cost-saving{color:var(--green);font-size:10px;display:none;margin-left:4px}
table.rpt .col-filter input{width:100%;border:1px solid #e2e8f0;border-radius:5px;padding:4px 6px;font-size:11px;background:#f8fafc;outline:none}
table.rpt thead .col-filter th{background:#1e293b;padding:5px 8px}
.no-data{text-align:center;padding:48px;color:#94a3b8;font-size:14px}
.export-btn{background:#10b981;color:#fff;border:none;border-radius:8px;padding:7px 14px;font-size:12px;font-weight:600;cursor:pointer}
</style>

<div class="rpt-header">📊 Combined Profit Report</div>
<div class="rpt-sub">eBay + Eshop orders — revenue, cost, postage, fees & profit in one view</div>

<div class="kpi-grid">
  <div class="kpi-card blue"><div class="kpi-icon">💰</div><div class="kpi-label">Total Revenue</div><div class="kpi-value">€{{ total_revenue }}</div><div class="kpi-sub">{{ row_count }} line items</div></div>
  <div class="kpi-card yellow"><div class="kpi-icon">🏭</div><div class="kpi-label">Total Cost</div><div class="kpi-value">€{{ total_cost }}</div></div>
  <div class="kpi-card slate"><div class="kpi-icon">📦</div><div class="kpi-label">Total Postage</div><div class="kpi-value">€{{ total_postage }}</div></div>
  <div class="kpi-card red"><div class="kpi-icon">🏷️</div><div class="kpi-label">Total Fees</div><div class="kpi-value">€{{ total_fee }}</div></div>
  <div class="kpi-card {% if total_profit >= 0 %}green{% else %}red{% endif %}"><div class="kpi-icon">📈</div><div class="kpi-label">Net Profit</div><div class="kpi-value">€{{ total_profit }}</div><div class="kpi-sub">{{ profit_pct_avg }}% margin</div></div>
  <div class="kpi-card slate"><div class="kpi-icon">🛒</div><div class="kpi-label">Orders / Units</div><div class="kpi-value">{{ total_orders }}</div><div class="kpi-sub">{{ total_units }} units sold</div></div>
</div>

<form class="filter-bar" method="get">
  <div><label>From Date</label><input type="date" name="date_from" value="{{ date_from }}"></div>
  <div><label>To Date</label><input type="date" name="date_to" value="{{ date_to }}"></div>
  <div><label>Source</label>
    <select name="source">
      <option value="all" {% if source_filter == 'all' %}selected{% endif %}>All Sources</option>
      <option value="ebay" {% if source_filter == 'ebay' %}selected{% endif %}>eBay Only</option>
      <option value="eshop" {% if source_filter == 'eshop' %}selected{% endif %}>Eshop Only</option>
    </select>
  </div>
  <input type="hidden" name="sort" value="{{ sort_by }}">
  <input type="hidden" name="dir" value="{{ sort_dir }}">
  <button type="submit" class="btn-filter">🔍 Apply</button>
  <a href="?" class="btn-clear">✕ Clear</a>
</form>

<div class="chart-card">
  <div class="chart-title">Monthly Revenue vs Cost vs Profit</div>
  <canvas id="mainChart" height="70"></canvas>
</div>

<div class="tbl-wrap">
  <div class="tbl-toolbar">
    <div class="tbl-toolbar-title">Order Lines <span style="color:#94a3b8;font-weight:400;font-size:12px;">— {{ row_count }} rows</span></div>
    <div style="display:flex;gap:10px;align-items:center;">
      <input class="tbl-search" id="tableSearch" placeholder="🔍 Search orders..." oninput="filterTable()">
      <button class="export-btn" onclick="exportCSV()">⬇️ Export CSV</button>
    </div>
  </div>
  <div style="overflow-x:auto;">
  <table class="rpt" id="mainTable">
    <thead>
      <tr>
        <th onclick="sortTable('date')" class="{% if sort_by == 'date' %}sorted{% endif %}">Date {% if sort_by == 'date' %}{% if sort_dir == 'desc' %}▼{% else %}▲{% endif %}{% endif %}</th>
        <th>Source</th>
        <th>Order Ref</th>
        <th onclick="sortTable('customer')" class="{% if sort_by == 'customer' %}sorted{% endif %}">Customer</th>
        <th>Country</th>
        <th>SKU</th>
        <th>Product</th>
        <th>Qty</th>
        <th onclick="sortTable('revenue')" class="{% if sort_by == 'revenue' %}sorted{% endif %}">Revenue</th>
        <th onclick="sortTable('cost')" class="{% if sort_by == 'cost' %}sorted{% endif %}">Cost</th>
        <th>Postage</th>
        <th>Fee</th>
        <th onclick="sortTable('profit')" class="{% if sort_by == 'profit' %}sorted{% endif %}">Profit</th>
        <th onclick="sortTable('profit_pct')" class="{% if sort_by == 'profit_pct' %}sorted{% endif %}">Margin</th>
      </tr>
      <tr class="col-filter">
        <th><input placeholder="Date..." oninput="colFilter(0,this.value)"></th>
        <th><input placeholder="Source..." oninput="colFilter(1,this.value)"></th>
        <th><input placeholder="Order..." oninput="colFilter(2,this.value)"></th>
        <th><input placeholder="Customer..." oninput="colFilter(3,this.value)"></th>
        <th><input placeholder="Country..." oninput="colFilter(4,this.value)"></th>
        <th><input placeholder="SKU..." oninput="colFilter(5,this.value)"></th>
        <th><input placeholder="Product..." oninput="colFilter(6,this.value)"></th>
        <th></th><th></th><th></th><th></th><th></th><th></th><th></th>
      </tr>
    </thead>
    <tbody id="tableBody">
    {% for r in rows %}
    <tr>
      <td class="mono">{{ r.date }}</td>
      <td><span class="src-pill {{ r.source_badge }}">{{ r.source }}</span></td>
      <td class="mono" style="font-size:11px;">{{ r.order_ref }}</td>
      <td>{{ r.customer }}</td>
      <td>{{ r.country }}</td>
      <td class="mono">{{ r.sku }}</td>
      <td style="max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="{{ r.product }}">{{ r.product }}</td>
      <td class="mono">{{ r.qty }}</td>
      <td class="mono">€{{ r.revenue }}</td>
      <td class="cost-cell">
        {% if r.source_badge == 'ebay' %}
        <input class="cost-input" type="number" step="0.01" value="{{ r.cost }}" onchange="saveCost(this,{{ r.id }},'{{ r.source_badge }}')" data-original="{{ r.cost }}">
        <span class="cost-saving" id="saving-{{ r.id }}">✓</span>
        {% else %}
        <span class="mono">€{{ r.cost }}</span>
        {% endif %}
      </td>
      <td class="mono">€{{ r.postage }}</td>
      <td class="mono">€{{ r.fee }}</td>
      <td><span class="profit-badge {% if r.profit > 0 %}pos{% elif r.profit < 0 %}neg{% else %}zero{% endif %}">€{{ r.profit }}</span></td>
      <td><span class="profit-badge {% if r.profit_pct > 20 %}pos{% elif r.profit_pct > 0 %}zero{% else %}neg{% endif %}">{{ r.profit_pct }}%</span></td>
    </tr>
    {% empty %}
    <tr><td colspan="14" class="no-data">No orders found for selected filters.</td></tr>
    {% endfor %}
    </tbody>
    <tfoot>
      <tr>
        <td colspan="8">TOTAL ({{ row_count }} rows)</td>
        <td>€{{ total_revenue }}</td>
        <td>€{{ total_cost }}</td>
        <td>€{{ total_postage }}</td>
        <td>€{{ total_fee }}</td>
        <td>€{{ total_profit }}</td>
        <td>{{ profit_pct_avg }}%</td>
      </tr>
    </tfoot>
  </table>
  </div>
</div>

<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/3.9.1/chart.min.js"></script>
<script>
new Chart(document.getElementById('mainChart'),{
  type:'bar',
  data:{
    labels:{{ chart_labels|safe }},
    datasets:[
      {label:'Revenue',data:{{ chart_revenue|safe }},backgroundColor:'rgba(59,130,246,0.7)',borderRadius:4},
      {label:'Cost',data:{{ chart_cost|safe }},backgroundColor:'rgba(245,158,11,0.7)',borderRadius:4},
      {label:'Profit',data:{{ chart_profit|safe }},backgroundColor:'rgba(16,185,129,0.7)',borderRadius:4},
    ]
  },
  options:{responsive:true,plugins:{legend:{position:'top'}},scales:{x:{grid:{display:false}},y:{beginAtZero:true,grid:{color:'#f1f5f9'}}}}
});
function filterTable(){
  const q=document.getElementById('tableSearch').value.toLowerCase();
  document.querySelectorAll('#tableBody tr').forEach(r=>r.style.display=r.textContent.toLowerCase().includes(q)?'':'none');
  updateFooter();
}
const colFilters={};
function colFilter(col,val){
  colFilters[col]=val.toLowerCase();
  document.querySelectorAll('#tableBody tr').forEach(row=>{
    let ok=true;
    Object.entries(colFilters).forEach(([c,v])=>{if(v&&row.cells[c]&&!row.cells[c].textContent.toLowerCase().includes(v))ok=false;});
    row.style.display=ok?'':'none';
  });
  updateFooter();
}
function sortTable(col){
  const url=new URL(window.location);
  url.searchParams.set('sort',col);
  url.searchParams.set('dir',('{{ sort_by }}'===col&&'{{ sort_dir }}'==='desc')?'asc':'desc');
  window.location=url;
}
function saveCost(input,id,source){
  fetch(window.location.pathname,{
    method:'POST',
    headers:{'Content-Type':'application/json','X-Requested-With':'XMLHttpRequest','X-CSRFToken':getCookie('csrftoken')},
    body:JSON.stringify({id,source,cost:parseFloat(input.value)})
  }).then(r=>r.json()).then(d=>{
    if(d.ok){const m=document.getElementById('saving-'+id);if(m){m.style.display='inline';setTimeout(()=>m.style.display='none',2000);}}
  });
}
function getCookie(n){const v=document.cookie.match('(^|;) ?'+n+'=([^;]*)(;|$)');return v?v[2]:null;}
function updateFooter(){
  let rev=0,cost=0,post=0,fee=0,profit=0,count=0;
  document.querySelectorAll('#tableBody tr').forEach(row=>{
    if(row.style.display!=='none'){
      const c=row.cells;
      rev+=parseFloat(c[8]?.textContent.replace('€','')||0);
      const ci=c[9]?.querySelector('input');
      cost+=parseFloat(ci?ci.value:(c[9]?.textContent.replace('€','')||0));
      post+=parseFloat(c[10]?.textContent.replace('€','')||0);
      fee+=parseFloat(c[11]?.textContent.replace('€','')||0);
      profit+=parseFloat(c[12]?.textContent.replace(/[€]/g,'')||0);
      count++;
    }
  });
  const f=document.querySelector('tfoot tr');
  if(f){
    f.cells[0].textContent='TOTAL ('+count+' rows)';
    f.cells[1].textContent='€'+rev.toFixed(2);
    f.cells[2].textContent='€'+cost.toFixed(2);
    f.cells[3].textContent='€'+post.toFixed(2);
    f.cells[4].textContent='€'+fee.toFixed(2);
    f.cells[5].textContent='€'+profit.toFixed(2);
    f.cells[6].textContent=rev>0?(profit/rev*100).toFixed(1)+'%':'0%';
  }
}
function exportCSV(){
  const rows=[['Date','Source','Order Ref','Customer','Country','SKU','Product','Qty','Revenue','Cost','Postage','Fee','Profit','Margin%']];
  document.querySelectorAll('#tableBody tr').forEach(row=>{
    if(row.style.display!=='none'){
      const c=row.cells;
      const ci=c[9]?.querySelector('input');
      rows.push([c[0].textContent.trim(),c[1].textContent.trim(),c[2].textContent.trim(),c[3].textContent.trim(),c[4].textContent.trim(),c[5].textContent.trim(),c[6].textContent.trim(),c[7].textContent.trim(),c[8].textContent.trim(),ci?ci.value:c[9].textContent.trim(),c[10].textContent.trim(),c[11].textContent.trim(),c[12].textContent.trim(),c[13].textContent.trim()]);
    }
  });
  const csv=rows.map(r=>r.map(v=>'"'+v+'"').join(',')).join('\\n');
  const a=document.createElement('a');
  a.href='data:text/csv;charset=utf-8,'+encodeURIComponent(csv);
  a.download='profit_report.csv';
  a.click();
}
</script>
{% endblock %}
""")
template.close()
print("✅ Template created successfully!")
