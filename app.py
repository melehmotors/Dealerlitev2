
import os, datetime
from pathlib import Path
from flask import Flask, request, send_file, redirect, url_for, flash, Response, render_template_string
from functools import wraps
from pdfrw import PdfReader, PdfWriter, PdfDict

# ================== Inline UI with client-side PDF417 scan ==================
INDEX_HTML = \"\"\"<!doctype html>
<html>
<head>
  <meta charset=\"utf-8\">
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
  <title>Meleh Motors — DealerLite</title>
  <style>
  body { font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif; background:#f7f7fb; }
  .wrap { max-width: 900px; margin: 20px auto; background: #fff; padding: 18px 18px; border-radius: 12px; box-shadow: 0 10px 30px rgba(0,0,0,.06); }
  h1 { margin: 6px 0 12px; }
  .card { background: #fafafa; border: 1px solid #eee; padding: 14px; border-radius: 8px; }
  .grid { display: grid; grid-template-columns: repeat(2, minmax(0,1fr)); gap: 12px; }
  label { display:block; margin: 8px 0; }
  input, textarea, button, select { width: 100%; padding: 10px; border:1px solid #ddd; border-radius: 6px; box-sizing: border-box; }
  button { cursor: pointer; font-weight: 600; }
  .or { text-align:center; margin: 10px 0; color:#888; }
  .flash { list-style: none; padding:0; }
  .flash li { padding:8px 10px; border-radius:6px; margin:8px 0; }
  .flash li.error { background:#ffe3e3; border:1px solid #ffc8c8; }
  .tiny { color:#888; font-size: 12px; margin-top: 12px; }
  #preview { width: 100%; border-radius: 10px; background:#000; }
  .row { display:flex; gap: 8px; align-items:center; flex-wrap: wrap; }
  .row > * { flex: 1 1 auto; }
  .pill { display:inline-block; background:#eef5ff; border:1px solid #d7e7ff; color:#225; padding:6px 10px; border-radius: 99px; font-size:12px; }
  .ok { color: #067d00; }
  .bad { color: #b00020; }
  </style>
  <!-- ZXing for in-browser PDF417 decoding -->
  <script src=\"https://unpkg.com/@zxing/browser@latest\"></script>
</head>
<body>
  <div class=\"wrap\">
    <h1>Meleh Motors — DealerLite</h1>
    <p class=\"pill\">Tip: Use <b>Scan with Phone Camera</b> for easiest decoding on iPhone. It fills the box automatically.</p>

    {% with messages = get_flashed_messages(with_categories=true) %}
      {% if messages %}
        <ul class=\"flash\">
          {% for category, message in messages %}
            <li class=\"{{ category }}\">{{ message }}</li>
          {% endfor %}
        </ul>
      {% endif %}
    {% endwith %}

    <form id=\"mainForm\" action=\"{{ url_for('scan') }}\" method=\"post\" enctype=\"multipart/form-data\" class=\"card\">
      <h2>1) Customer ID</h2>

      <div class=\"row\">
        <button type=\"button\" id=\"startScan\">📷 Scan with Phone Camera</button>
        <select id=\"cameraSelect\" style=\"display:none\"></select>
        <span id=\"scanStatus\" class=\"\"></span>
      </div>
      <video id=\"preview\" playsinline muted style=\"display:none;\"></video>

      <div class=\"or\">— OR —</div>

      <label>Upload license back photo (server-side decode): <input type=\"file\" name=\"license_image\" accept=\"image/*\" capture=\"environment\"></label>

      <label>Raw AAMVA payload (auto-filled by scanner):<br>
        <textarea id=\"payload_text\" name=\"payload_text\" rows=\"6\" placeholder=\"If the scanner reads the barcode, the text appears here automatically.\"></textarea>
      </label>

      <h2>2) Contact Info</h2>
      <div class=\"grid\">
        <label>Phone <input name=\"phone\"></label>
        <label>Email <input name=\"email\"></label>
      </div>

      <h2>3) Vehicle</h2>
      <div class=\"grid\">
        <label>VIN <input name=\"vin\"></label>
        <label>Year <input name=\"year\"></label>
        <label>Make <input name=\"make\"></label>
        <label>Model <input name=\"model\"></label>
      </div>
      <label>Vehicle (Year/Make/Model) — for waiver <input name=\"ymm\" placeholder=\"e.g., 2017 Toyota Camry SE\"></label>

      <h2>4) Sale</h2>
      <div class=\"grid\">
        <label>Sale Price <input name=\"price\"></label>
        <label>Sale Date <input name=\"sale_date\" type=\"date\"></label>
      </div>

      <button type=\"submit\">Generate PDFs</button>
    </form>

    <p class=\"tiny\">Your data stays on this server. If login is on, you'll be prompted first.</p>
  </div>

<script>
  const startBtn = document.getElementById('startScan');
  const video = document.getElementById('preview');
  const cameraSelect = document.getElementById('cameraSelect');
  const payloadBox = document.getElementById('payload_text');
  const scanStatus = document.getElementById('scanStatus');

  let codeReader = null;
  let currentControls = null;

  function setStatus(text, ok=false) {
    scanStatus.textContent = text;
    scanStatus.className = ok ? 'ok' : 'bad';
  }

  async function listCameras() {
    const devices = await ZXing.BrowserCodeReader.listVideoInputDevices();
    cameraSelect.innerHTML = '';
    devices.forEach(d => {
      const opt = document.createElement('option');
      opt.value = d.deviceId;
      opt.textContent = d.label || 'Camera';
      cameraSelect.appendChild(opt);
    });
    return devices;
  }

  async function startCamera(deviceId) {
    try {
      if (currentControls) { currentControls.stop(); currentControls = null; }
      video.style.display = 'block';
      cameraSelect.style.display = 'inline-block';
      if (!codeReader) {
        codeReader = new ZXing.BrowserPDF417Reader();
      }
      currentControls = await ZXing.BrowserCodeReader.decodeFromVideoDevice(
        deviceId || null,
        video,
        (result, err, ctrl) => {
          if (result) {
            payloadBox.value = result.getText();
            setStatus('Decoded ✅', true);
            ctrl.stop();
            currentControls = null;
          } else if (err && !(err instanceof ZXing.NotFoundException)) {
            setStatus('Scanning…');
          }
        }
      );
      setStatus('Scanning…');
    } catch (e) {
      setStatus('Camera error: ' + e, false);
    }
  }

  startBtn.addEventListener('click', async () => {
    try {
      await listCameras();
      const preferBack = Array.from(cameraSelect.options).find(o => /back|rear/i.test(o.textContent));
      if (preferBack) cameraSelect.value = preferBack.value;
      startCamera(cameraSelect.value);
    } catch (e) {
      setStatus('Permission needed for camera: ' + e, false);
    }
  });

  cameraSelect.addEventListener('change', () => startCamera(cameraSelect.value));
</script>
</body>
</html>\"\"\"

DONE_HTML = \"\"\"<!doctype html>
<html>
<head>
  <meta charset=\"utf-8\">
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
  <title>DealerLite — Done</title>
  <style>
  body { font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif; background:#f7f7fb; }
  .wrap { max-width: 860px; margin: 20px auto; background: #fff; padding: 24px 28px; border-radius: 12px; box-shadow: 0 10px 30px rgba(0,0,0,.06); }
  h1 { margin-top: 0; }
  </style>
</head>
<body>
  <div class=\"wrap\">
    <h1>Forms ready ✅</h1>
    <p>Download your filled PDFs:</p>
    <ul>
      <li><a href=\"{{ url_for('download', which='waiver') }}\">Test Drive Waiver</a></li>
      <li><a href=\"{{ url_for('download', which='bos') }}\">Bill of Sale</a></li>
    </ul>
    <p><a href=\"{{ url_for('index') }}\">Back</a></p>
  </div>
</body>
</html>\"\"\"

def parse_aamva(raw: str):
    from datetime import datetime as _dt
    lines = [l for l in raw.splitlines() if l.strip()]
    lookup = {}
    for l in lines:
        key = l[:3]; val = l[3:]
        if key.isalpha():
            lookup[key] = val.strip()
    def norm_date(s: str) -> str:
        s = s.strip()
        for fmt in (\"%Y%m%d\", \"%m%d%Y\", \"%Y-%m-%d\"):
            try:
                return _dt.strptime(s, fmt).strftime(\"%Y-%m-%d\")
            except Exception:
                pass
        return s
    data = {}
    data[\"last_name\"]   = lookup.get(\"DCS\",\"\");
    data[\"first_name\"]  = lookup.get(\"DAC\",\"\");
    data[\"middle_name\"] = lookup.get(\"DAD\",\"\");
    data[\"name\"]        = lookup.get(\"DCT\") or \" \".join([data[\"first_name\"], data[\"middle_name\"], data[\"last_name\"]]).strip()
    data[\"dob\"]         = norm_date(lookup.get(\"DBB\",\"\"))
    data[\"expiry_date\"] = norm_date(lookup.get(\"DBA\",\"\"))
    data[\"issue_date\"]  = norm_date(lookup.get(\"DBD\",\"\"))
    data[\"street\"]      = lookup.get(\"DAG\",\"\");
    data[\"city\"]        = lookup.get(\"DAI\",\"\");
    data[\"state\"]       = lookup.get(\"DAJ\",\"\");
    data[\"postal_code\"] = (lookup.get(\"DAK\",\"\") or \"\").replace(\"-\",\"\" ).strip()
    data[\"license_number\"] = lookup.get(\"DAQ\",\"\");
    return data

def decode_pdf417(image_path: str):
    try:
        from pyzbar.pyzbar import decode, ZBarSymbol
    except Exception as e:
        return None, (\"Server decoder not available. Use the phone camera scanner above, or paste payload. Detail: %s\" % e)
    from PIL import Image
    try:
        img = Image.open(image_path)
    except Exception as e:
        return None, f\"Failed to open image: {e}\"
    try:
        results = decode(img, symbols=[ZBarSymbol.PDF417])
        for r in results:
            data = r.data.decode(\"utf-8\", errors=\"ignore\")
            if data:
                return data, \"OK\"
        return None, \"No PDF417 found in image.\"
    except Exception as e:
        return None, f\"Decode error: {e}\"

ANNOT_KEY = '/Annots'
WIDGET_SUBTYPE_KEY = '/Subtype'
WIDGET_SUBTYPE = '/Widget'
ANNOT_FIELD_KEY = '/T'
ANNOT_APPEARANCE_KEY = '/AP'

def fill_pdf(input_pdf_path: str, output_pdf_path: str, data: dict):
    template_pdf = PdfReader(input_pdf_path)
    for page in template_pdf.pages:
        annotations = page.get(ANNOT_KEY)
        if annotations:
            for annotation in annotations:
                if annotation.get(WIDGET_SUBTYPE_KEY) == WIDGET_SUBTYPE and annotation.get(ANNOT_FIELD_KEY):
                    key = annotation.get(ANNOT_FIELD_KEY)[1:-1]
                    if key in data:
                        annotation.update(PdfDict(V=str(data[key])))
                        if annotation.get(ANNOT_APPEARANCE_KEY):
                            annotation[ANNOT_APPEARANCE_KEY] = PdfDict()
    PdfWriter().write(output_pdf_path, template_pdf)

def to_test_drive_waiver(aamva: dict) -> dict:
    return {
        \"FullName\": aamva.get(\"name\",\"\"),
        \"FirstName\": aamva.get(\"first_name\",\"\"),
        \"LastName\": aamva.get(\"last_name\",\"\"),
        \"DOB\": aamva.get(\"dob\",\"\"),
        \"DLNumber\": aamva.get(\"license_number\",\"\"),
        \"Address\": f\"{aamva.get('street','')}, {aamva.get('city','')}, {aamva.get('state','')} {aamva.get('postal_code','')}\".strip().strip(\", \"),
        \"Phone\": \"\",
        \"Email\": \"\",
        \"VehicleVIN\": \"\",
        \"VehicleYearMakeModel\": \"\",
    }

def to_bill_of_sale(aamva: dict) -> dict:
    return {
        \"BuyerFullName\": aamva.get(\"name\",\"\"),
        \"BuyerAddress\": f\"{aamva.get('street','')}, {aamva.get('city','')}, {aamva.get('state','')} {aamva.get('postal_code','')}\".strip().strip(\", \"),
        \"BuyerDL\": aamva.get(\"license_number\",\"\"),
        \"BuyerDOB\": aamva.get(\"dob\",\"\"),
        \"VehicleVIN\": \"\",
        \"VehicleYear\": \"\",
        \"VehicleMake\": \"\",
        \"VehicleModel\": \"\",
        \"SalePrice\": \"\",
        \"SaleDate\": \"\",
    }

from dotenv import load_dotenv
load_dotenv()

UPLOAD_FOLDER = Path(\"uploads\")
OUT_FOLDER = Path(\"out\")
FORMS_FOLDER = Path(\"sample_forms\")

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.units import inch

def _ensure_dir(p: Path): p.mkdir(parents=True, exist_ok=True)

def _make_test_drive_waiver_template(path: Path):
    c = canvas.Canvas(str(path), pagesize=LETTER); width, height = LETTER
    c.setFont(\"Helvetica-Bold\", 16); c.drawString(1*inch, height-1*inch, \"Test Drive Waiver\")
    c.setFont(\"Helvetica\", 10); y = height - 1.5*inch
    fields = [(\"Full Name\",\"FullName\"),(\"First Name\",\"FirstName\"),(\"Last Name\",\"LastName\"),
              (\"Date of Birth\",\"DOB\"),(\"Driver License #\",\"DLNumber\"),(\"Address\",\"Address\"),
              (\"Phone\",\"Phone\"),(\"Email\",\"Email\"),(\"Vehicle (Year/Make/Model)\",\"VehicleYearMakeModel\"),
              (\"VIN\",\"VehicleVIN\")]
    for label, fname in fields:
        c.drawString(1*inch, y, label + \":\")
        c.acroForm.textfield(name=fname, tooltip=label, x=2.6*inch, y=y-4, width=3.8*inch, height=16, borderStyle=\"underlined\", forceBorder=True)
        y -= 0.4*inch
    c.drawString(1*inch, y, \"Customer Signature:\")
    c.acroForm.textfield(name=\"Signature\", x=2.6*inch, y=y-4, width=3.8*inch, height=16, borderStyle=\"underlined\", forceBorder=True)
    c.save()

def _make_bill_of_sale_template(path: Path):
    c = canvas.Canvas(str(path), pagesize=LETTER); width, height = LETTER
    c.setFont(\"Helvetica-Bold\", 16); c.drawString(1*inch, height-1*inch, \"Bill of Sale\")
    c.setFont(\"Helvetica\", 10); y = height - 1.5*inch
    fields = [(\"Buyer Full Name\",\"BuyerFullName\"),(\"Buyer Address\",\"BuyerAddress\"),
              (\"Buyer DL\",\"BuyerDL\"),(\"Buyer DOB\",\"BuyerDOB\"),
              (\"Vehicle VIN\",\"VehicleVIN\"),(\"Vehicle Year\",\"VehicleYear\"),
              (\"Vehicle Make\",\"VehicleMake\"),(\"Vehicle Model\",\"VehicleModel\"),
              (\"Sale Price\",\"SalePrice\"),(\"Sale Date\",\"SaleDate\")]
    for label, fname in fields:
        c.drawString(1*inch, y, label + \":\")
        c.acroForm.textfield(name=fname, tooltip=label, x=2.6*inch, y=y-4, width=3.8*inch, height=16, borderStyle=\"underlined\", forceBorder=True)
        y -= 0.4*inch
    c.save()

_ensure_dir(UPLOAD_FOLDER); _ensure_dir(OUT_FOLDER); _ensure_dir(FORMS_FOLDER)
if not (FORMS_FOLDER / \"test_drive_waiver_template.pdf\").exists():
    _make_test_drive_waiver_template(FORMS_FOLDER / \"test_drive_waiver_template.pdf\")
if not (FORMS_FOLDER / \"bill_of_sale_template.pdf\").exists():
    _make_bill_of_sale_template(FORMS_FOLDER / \"bill_of_sale_template.pdf\")

app = Flask(__name__)
app.secret_key = os.getenv(\"FLASK_SECRET\", \"dev-secret\")

BASIC_USER = os.getenv(\"BASIC_AUTH_USER\")
BASIC_PASS = os.getenv(\"BASIC_AUTH_PASS\")
def check_auth(username, password): return BASIC_USER and BASIC_PASS and username == BASIC_USER and password == BASIC_PASS
def authenticate(): return Response(\"Authentication required\", 401, {\"WWW-Authenticate\": 'Basic realm=\"Login\"'})
def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if BASIC_USER and BASIC_PASS:
            auth = request.authorization
            if not auth or not check_auth(auth.username, auth.password):
                return authenticate()
        return f(*args, **kwargs)
    return decorated

@app.get(\"/health\")
def health(): return {\"status\":\"ok\"}

@app.route(\"/\", methods=[\"GET\"])
@requires_auth
def index():
    return render_template_string(INDEX_HTML)

@app.route(\"/scan\", methods=[\"POST\"])
@requires_auth
def scan():
    img = request.files.get(\"license_image\")
    payload_text = request.form.get(\"payload_text\",\"\" ).strip()
    person = {}; err = None

    if payload_text:
        person = parse_aamva(payload_text)
    elif img and img.filename:
        path = UPLOAD_FOLDER / img.filename
        img.save(path)
        payload, msg = decode_pdf417(str(path))
        if not payload:
            err = f\"Could not decode PDF417 barcode: {msg}\"
        else:
            person = parse_aamva(payload)
    else:
        err = \"Use the camera scanner (preferred), upload a photo, or paste payload.\"
    if err:
        flash(err, \"error\"); return redirect(url_for(\"index\"))

    phone = request.form.get(\"phone\",\"\" ).strip()
    email = request.form.get(\"email\",\"\" ).strip()
    vin = request.form.get(\"vin\",\"\" ).strip()
    ymm = request.form.get(\"ymm\",\"\" ).strip()
    year = request.form.get(\"year\",\"\" ).strip()
    make = request.form.get(\"make\",\"\" ).strip()
    model = request.form.get(\"model\",\"\" ).strip()
    price = request.form.get(\"price\",\"\" ).strip()
    sale_date = request.form.get(\"sale_date\", datetime.date.today().isoformat())

    waiver_map = to_test_drive_waiver(person)
    waiver_map.update({\"Phone\":phone, \"Email\":email, \"VehicleVIN\":vin, \"VehicleYearMakeModel\":ymm})

    bos_map = to_bill_of_sale(person)
    bos_map.update({\"VehicleVIN\":vin, \"VehicleYear\":year, \"VehicleMake\":make, \"VehicleModel\":model,
                    \"SalePrice\":price, \"SaleDate\":sale_date})

    out_waiver = Path(\"out/test_drive_waiver_filled.pdf\")
    out_bos = Path(\"out/bill_of_sale_filled.pdf\")
    fill_pdf(str(Path(\"sample_forms/test_drive_waiver_template.pdf\")), str(out_waiver), waiver_map)
    fill_pdf(str(Path(\"sample_forms/bill_of_sale_template.pdf\")), str(out_bos), bos_map)
    return render_template_string(DONE_HTML)

@app.route(\"/download/<which>\")
@requires_auth
def download(which):
    if which == \"waiver\": path = Path(\"out/test_drive_waiver_filled.pdf\")
    elif which == \"bos\":  path = Path(\"out/bill_of_sale_filled.pdf\")
    else: return \"Not found\", 404
    if not path.exists(): return \"File not ready\", 404
    return send_file(path, as_attachment=True, download_name=path.name)

if __name__ == \"__main__\":
    app.run(host=\"0.0.0.0\", port=int(os.getenv(\"PORT\",\"5000\")), debug=False)
