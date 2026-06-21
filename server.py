import io
import csv
import json
from datetime import datetime
from flask import Flask, request, jsonify, send_file, render_template_string
from main import reconcile_data

app = Flask(__name__)

HTML = r"""
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>Balance Reconciliation</title>
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: #f0f2f5;
      color: #1a1a2e;
      min-height: 100vh;
    }

    header {
      background: linear-gradient(135deg, #1a1a2e 0%, #16213e 60%, #0f3460 100%);
      color: #fff;
      padding: 24px 32px;
      box-shadow: 0 2px 12px rgba(0,0,0,.3);
    }
    header h1 { font-size: 1.6rem; font-weight: 700; letter-spacing: .5px; }
    header p  { font-size: .85rem; opacity: .7; margin-top: 4px; }

    main { max-width: 1100px; margin: 32px auto; padding: 0 20px; }

    /* ── Upload card ── */
    .upload-card {
      background: #fff;
      border-radius: 12px;
      padding: 28px 32px;
      box-shadow: 0 1px 6px rgba(0,0,0,.08);
      margin-bottom: 28px;
    }
    .upload-card h2 { font-size: 1.05rem; font-weight: 600; margin-bottom: 20px; color: #16213e; }

    .drop-row {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 20px;
      margin-bottom: 20px;
    }

    .drop-zone {
      border: 2px dashed #c9d0e0;
      border-radius: 10px;
      padding: 28px 20px;
      text-align: center;
      cursor: pointer;
      transition: border-color .2s, background .2s;
      position: relative;
      background: #fafbfd;
    }
    .drop-zone:hover, .drop-zone.drag-over {
      border-color: #0f3460;
      background: #eef2ff;
    }
    .drop-zone.has-file {
      border-color: #22c55e;
      background: #f0fdf4;
    }
    .drop-zone input[type=file] {
      position: absolute; inset: 0; opacity: 0; cursor: pointer; width: 100%; height: 100%;
    }
    .drop-icon { font-size: 2rem; margin-bottom: 10px; }
    .drop-label { font-size: .9rem; font-weight: 600; color: #374151; }
    .drop-hint  { font-size: .75rem; color: #9ca3af; margin-top: 4px; }
    .drop-filename {
      font-size: .8rem; color: #16a34a; margin-top: 8px;
      font-weight: 600; display: none;
    }
    .drop-zone.has-file .drop-filename { display: block; }
    .drop-zone.has-file .drop-hint { display: none; }

    .btn-row { display: flex; gap: 12px; align-items: center; }

    .btn {
      display: inline-flex; align-items: center; gap: 8px;
      padding: 10px 22px; border-radius: 8px; font-size: .9rem;
      font-weight: 600; cursor: pointer; border: none; transition: all .15s;
    }
    .btn-primary {
      background: linear-gradient(135deg, #0f3460, #1a6fc4);
      color: #fff; box-shadow: 0 2px 8px rgba(15,52,96,.3);
    }
    .btn-primary:hover { filter: brightness(1.1); transform: translateY(-1px); }
    .btn-primary:disabled { opacity: .5; cursor: not-allowed; transform: none; filter: none; }
    .btn-outline {
      background: #fff; color: #0f3460;
      border: 1.5px solid #0f3460;
    }
    .btn-outline:hover { background: #eef2ff; }

    .spinner {
      display: none; width: 18px; height: 18px;
      border: 2px solid rgba(255,255,255,.4);
      border-top-color: #fff;
      border-radius: 50%;
      animation: spin .7s linear infinite;
    }
    @keyframes spin { to { transform: rotate(360deg); } }

    /* ── Summary banner ── */
    .summary-banner {
      display: none;
      border-radius: 10px;
      padding: 20px 24px;
      margin-bottom: 24px;
      box-shadow: 0 1px 6px rgba(0,0,0,.07);
    }
    .summary-banner.ok   { background: #f0fdf4; border-left: 5px solid #22c55e; }
    .summary-banner.bad  { background: #fff5f5; border-left: 5px solid #ef4444; }
    .summary-banner h3   { font-size: 1rem; font-weight: 700; margin-bottom: 10px; }
    .banner-ok-title  { color: #15803d; }
    .banner-bad-title { color: #b91c1c; }

    .summary-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
      gap: 10px;
      margin-top: 12px;
    }
    .stat-box {
      background: rgba(255,255,255,.7);
      border-radius: 8px;
      padding: 12px 14px;
    }
    .stat-label { font-size: .72rem; text-transform: uppercase; letter-spacing: .6px; color: #6b7280; }
    .stat-value { font-size: 1.1rem; font-weight: 700; margin-top: 3px; }

    .disc-list { margin-top: 14px; }
    .disc-list h4 { font-size: .85rem; font-weight: 600; color: #b91c1c; margin-bottom: 6px; }
    .disc-list ul { list-style: none; display: flex; flex-wrap: wrap; gap: 8px; }
    .disc-list li {
      background: #fee2e2; color: #991b1b;
      font-size: .78rem; font-weight: 600;
      padding: 4px 10px; border-radius: 20px;
    }
    .warning-box {
      background: #fffbeb; border: 1px solid #fcd34d; border-radius: 8px;
      padding: 10px 14px; font-size: .82rem; color: #92400e; margin-top: 10px;
    }

    /* ── Report table ── */
    .report-card {
      display: none;
      background: #fff;
      border-radius: 12px;
      box-shadow: 0 1px 6px rgba(0,0,0,.08);
      overflow: hidden;
    }
    .report-header {
      display: flex; align-items: center; justify-content: space-between;
      padding: 18px 24px;
      border-bottom: 1px solid #f0f2f5;
    }
    .report-header h2 { font-size: 1rem; font-weight: 600; }

    .table-wrap { overflow-x: auto; }
    table { width: 100%; border-collapse: collapse; font-size: .87rem; }
    th {
      background: #1a1a2e; color: #e5e7eb;
      padding: 11px 16px; text-align: left;
      font-size: .78rem; text-transform: uppercase; letter-spacing: .6px;
      font-weight: 600; white-space: nowrap;
    }
    td { padding: 10px 16px; border-bottom: 1px solid #f0f2f5; white-space: nowrap; }
    tr:last-child td { border-bottom: none; }

    tr.ok   td { background: #f0fdf4; }
    tr.bad  td { background: #fff5f5; }
    tr.none td { background: #fafafa; }

    .badge {
      display: inline-block; padding: 2px 9px;
      border-radius: 20px; font-size: .72rem; font-weight: 700;
    }
    .badge-ok   { background: #dcfce7; color: #15803d; }
    .badge-bad  { background: #fee2e2; color: #b91c1c; }
    .badge-none { background: #f3f4f6; color: #6b7280; }

    .num { text-align: right; font-variant-numeric: tabular-nums; }

    .error-box {
      background: #fff1f2; border: 1.5px solid #fca5a5;
      border-radius: 10px; padding: 16px 20px;
      color: #b91c1c; font-size: .88rem; display: none; margin-bottom: 20px;
    }

    @media (max-width: 640px) {
      .drop-row { grid-template-columns: 1fr; }
      .summary-grid { grid-template-columns: 1fr 1fr; }
    }
  </style>
</head>
<body>

<header>
  <h1>Balance Reconciliation</h1>
  <p>Upload your transaction and bank balance files to generate a reconciliation report</p>
</header>

<main>

  <!-- Upload card -->
  <div class="upload-card">
    <h2>Upload CSV Files</h2>
    <div class="drop-row">
      <div class="drop-zone" id="dropTx" ondragover="onDragOver(event,'dropTx')"
           ondragleave="onDragLeave(event,'dropTx')" ondrop="onDrop(event,'fileTx','dropTx','nameTx')">
        <input type="file" id="fileTx" accept=".csv" onchange="onFileChange('fileTx','dropTx','nameTx')"/>
        <div class="drop-icon">📄</div>
        <div class="drop-label">transactions.csv</div>
        <div class="drop-hint">Drag &amp; drop or click to browse</div>
        <div class="drop-filename" id="nameTx"></div>
      </div>

      <div class="drop-zone" id="dropBk" ondragover="onDragOver(event,'dropBk')"
           ondragleave="onDragLeave(event,'dropBk')" ondrop="onDrop(event,'fileBk','dropBk','nameBk')">
        <input type="file" id="fileBk" accept=".csv" onchange="onFileChange('fileBk','dropBk','nameBk')"/>
        <div class="drop-icon">🏦</div>
        <div class="drop-label">bank_balances.csv</div>
        <div class="drop-hint">Drag &amp; drop or click to browse</div>
        <div class="drop-filename" id="nameBk"></div>
      </div>
    </div>

    <div class="btn-row">
      <button class="btn btn-primary" id="btnReconcile" onclick="reconcile()" disabled>
        <span id="btnIcon">⚡</span>
        <span id="btnText">Reconcile</span>
        <div class="spinner" id="spinner"></div>
      </button>
    </div>
  </div>

  <div class="error-box" id="errorBox"></div>

  <!-- Summary banner -->
  <div class="summary-banner" id="summaryBanner">
    <h3 id="bannerTitle"></h3>
    <div class="summary-grid" id="summaryGrid"></div>
    <div class="disc-list" id="discList"></div>
    <div class="warning-box" id="warningBox" style="display:none"></div>
  </div>

  <!-- Report table -->
  <div class="report-card" id="reportCard">
    <div class="report-header">
      <h2>Day-by-Day Statement Log</h2>
      <div class="btn-row">
        <button class="btn btn-outline" onclick="download()">⬇ Download CSV</button>
      </div>
    </div>
    <div class="table-wrap">
      <table id="reportTable">
        <thead>
          <tr>
            <th>Date</th>
            <th class="num">Running Balance</th>
            <th class="num">Bank Balance</th>
            <th class="num">Discrepancy</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody id="reportBody"></tbody>
      </table>
    </div>
  </div>

</main>

<script>
let lastResult = null;

/* ── Drag-and-drop helpers ── */
function onDragOver(e, zoneId) {
  e.preventDefault();
  document.getElementById(zoneId).classList.add('drag-over');
}
function onDragLeave(e, zoneId) {
  document.getElementById(zoneId).classList.remove('drag-over');
}
function onDrop(e, inputId, zoneId, nameId) {
  e.preventDefault();
  const zone = document.getElementById(zoneId);
  zone.classList.remove('drag-over');
  const file = e.dataTransfer.files[0];
  if (!file) return;
  const dt = new DataTransfer();
  dt.items.add(file);
  document.getElementById(inputId).files = dt.files;
  markFile(zoneId, nameId, file.name);
}
function onFileChange(inputId, zoneId, nameId) {
  const f = document.getElementById(inputId).files[0];
  if (f) markFile(zoneId, nameId, f.name);
}
function markFile(zoneId, nameId, name) {
  document.getElementById(zoneId).classList.add('has-file');
  document.getElementById(nameId).textContent = '✓ ' + name;
  checkReady();
}
function checkReady() {
  const txOk = document.getElementById('fileTx').files.length > 0;
  const bkOk = document.getElementById('fileBk').files.length > 0;
  document.getElementById('btnReconcile').disabled = !(txOk && bkOk);
}

/* ── Reconcile ── */
async function reconcile() {
  const txFile = document.getElementById('fileTx').files[0];
  const bkFile = document.getElementById('fileBk').files[0];
  if (!txFile || !bkFile) return;

  setLoading(true);
  hideResults();

  const fd = new FormData();
  fd.append('transactions', txFile);
  fd.append('bank_balances', bkFile);

  try {
    const res = await fetch('/reconcile', { method: 'POST', body: fd });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Unknown error');
    lastResult = data;
    renderResults(data);
  } catch (err) {
    showError(err.message);
  } finally {
    setLoading(false);
  }
}

function setLoading(on) {
  document.getElementById('spinner').style.display = on ? 'block' : 'none';
  document.getElementById('btnIcon').style.display  = on ? 'none'  : 'inline';
  document.getElementById('btnText').textContent = on ? 'Processing…' : 'Reconcile';
  document.getElementById('btnReconcile').disabled = on;
}

function hideResults() {
  document.getElementById('errorBox').style.display = 'none';
  document.getElementById('summaryBanner').style.display = 'none';
  document.getElementById('reportCard').style.display = 'none';
}

function showError(msg) {
  const box = document.getElementById('errorBox');
  box.textContent = '⚠ ' + msg;
  box.style.display = 'block';
}

/* ── Render ── */
function fmt(n) {
  if (n == null) return '—';
  return n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function renderResults(data) {
  const { rows, mismatch_count, warning, summary } = data;
  const all_match = mismatch_count === 0;

  /* Summary banner */
  const banner = document.getElementById('summaryBanner');
  banner.className = 'summary-banner ' + (all_match ? 'ok' : 'bad');

  const title = document.getElementById('bannerTitle');
  title.className = all_match ? 'banner-ok-title' : 'banner-bad-title';
  title.textContent = all_match
    ? '✓ All balances match — no discrepancies found'
    : `✗ ${mismatch_count} discrepanc${mismatch_count === 1 ? 'y' : 'ies'} detected`;

  const grid = document.getElementById('summaryGrid');
  grid.innerHTML = [
    ['Final Running Balance', '$' + fmt(summary.final_running_balance)],
    ['Final Bank Balance',    '$' + fmt(summary.final_bank_balance)],
    ['Net Discrepancy',       '$' + fmt(summary.net_discrepancy)],
    ['Days Reviewed',         rows.length],
    ['Days with Mismatch',    summary.discrepancies.length],
  ].map(([label, val]) => `
    <div class="stat-box">
      <div class="stat-label">${label}</div>
      <div class="stat-value">${val}</div>
    </div>`).join('');

  const discList = document.getElementById('discList');
  if (summary.discrepancies.length > 0) {
    discList.innerHTML = `
      <h4>Days with discrepancies</h4>
      <ul>${summary.discrepancies.map(d =>
        `<li>${d.date} &nbsp;($${fmt(d.discrepancy)})</li>`).join('')}
      </ul>`;
    discList.style.display = 'block';
  } else {
    discList.style.display = 'none';
  }

  const warnBox = document.getElementById('warningBox');
  if (warning) {
    warnBox.textContent = '⚠ ' + warning;
    warnBox.style.display = 'block';
  } else {
    warnBox.style.display = 'none';
  }

  banner.style.display = 'block';

  /* Report table */
  const tbody = document.getElementById('reportBody');
  tbody.innerHTML = rows.map(r => {
    const cls = r.status === 'OK' ? 'ok' : r.status === 'NO_RECORD' ? 'none' : 'bad';
    const badge = r.status === 'OK'
      ? '<span class="badge badge-ok">Match</span>'
      : r.status === 'NO_RECORD'
      ? '<span class="badge badge-none">No Record</span>'
      : '<span class="badge badge-bad">Mismatch</span>';
    return `<tr class="${cls}">
      <td>${r.date}</td>
      <td class="num">$${fmt(r.running)}</td>
      <td class="num">${r.bank != null ? '$' + fmt(r.bank) : '—'}</td>
      <td class="num">${r.discrepancy != null ? '$' + fmt(r.discrepancy) : '—'}</td>
      <td>${badge}</td>
    </tr>`;
  }).join('');

  document.getElementById('reportCard').style.display = 'block';
}

/* ── Download ── */
function download() {
  if (!lastResult) return;
  const url = '/download/csv';
  const form = document.createElement('form');
  form.method = 'POST';
  form.action = url;
  const inp = document.createElement('input');
  inp.type = 'hidden';
  inp.name = 'data';
  inp.value = JSON.stringify(lastResult);
  form.appendChild(inp);
  document.body.appendChild(form);
  form.submit();
  document.body.removeChild(form);
}
</script>
</body>
</html>
"""


@app.route("/")
def index():
    return render_template_string(HTML)


@app.route("/reconcile", methods=["POST"])
def reconcile():
    tx_file = request.files.get("transactions")
    bk_file = request.files.get("bank_balances")
    if not tx_file or not bk_file:
        return jsonify({"error": "Both files are required"}), 400
    try:
        tx_text = tx_file.read().decode("utf-8-sig")
        bk_text = bk_file.read().decode("utf-8-sig")
        result = reconcile_data(tx_text, bk_text)
        return jsonify(result)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": f"Processing error: {e}"}), 500


@app.route("/download/csv", methods=["POST"])
def download_csv():
    try:
        data = json.loads(request.form["data"])
        rows = data["rows"]
        summary = data["summary"]
    except (KeyError, json.JSONDecodeError) as e:
        return jsonify({"error": f"Invalid download payload: {e}"}), 400
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    buf = io.StringIO()
    w = csv.writer(buf)

    w.writerow(["=== SUMMARY ==="])
    w.writerow(["Final Running Balance", summary["final_running_balance"]])
    w.writerow(["Final Bank Balance",    summary["final_bank_balance"]])
    w.writerow(["Net Discrepancy",       summary["net_discrepancy"]])
    w.writerow([])
    if summary["discrepancies"]:
        w.writerow(["=== DISCREPANCY DATES ==="])
        w.writerow(["Date", "Discrepancy"])
        for d in summary["discrepancies"]:
            w.writerow([d["date"], d["discrepancy"]])
        w.writerow([])

    w.writerow(["=== DAY-BY-DAY REPORT ==="])
    w.writerow(["Date", "Running Balance", "Bank Balance", "Discrepancy", "Status"])
    for r in rows:
        w.writerow([
            r["date"],
            r["running"],
            r["bank"] if r["bank"] is not None else "",
            r["discrepancy"] if r["discrepancy"] is not None else "",
            r["status"],
        ])

    buf.seek(0)
    return send_file(
        io.BytesIO(buf.getvalue().encode("utf-8")),
        mimetype="text/csv",
        as_attachment=True,
        download_name=f"reconciliation_{ts}.csv",
    )


if __name__ == "__main__":
    app.run(debug=True, port=5000)
