"""The in-app User Guide content — one deep section per screen, with visual cues.

Mirrors the MicroFlex User Guide's structure (numbered sections, stable anchors,
step lists, flowchart symbols) but is written for MIA3 — a portfolio MONITOR,
not an applicant decisioner. Every app screen maps to a section here, so the
contextual "User guide" link in a screen's purpose banner opens this guide
scrolled to the part that explains that screen.

Bodies are trusted, author-written HTML rendered with |safe.
"""
from __future__ import annotations

from typing import Dict, List, Optional

# Band colours reused in the visual cues (match app/static/app.css).
C_VHIGH, C_HIGH, C_MOD, C_LOW = "#c0392b", "#e67e22", "#f1c40f", "#27ae60"
C_SDA, C_ACCENT = "#003A70", "#4B6EEC"  # CGC Blue, Royal Blue

# --- Reusable inline-SVG visual cues --------------------------------------
SYMBOLS_SVG = f"""
<svg viewBox="0 0 720 90" class="g-svg" role="img" aria-label="Flowchart symbols">
  <ellipse cx="80" cy="45" rx="64" ry="26" fill="#eaf2ff" stroke="{C_ACCENT}" stroke-width="2"/>
  <text x="80" y="49" text-anchor="middle" font-size="13">Terminator</text>
  <rect x="210" y="20" width="140" height="50" rx="6" fill="#fff" stroke="{C_SDA}" stroke-width="2"/>
  <text x="280" y="49" text-anchor="middle" font-size="13">Process</text>
  <polygon points="470,20 540,45 470,70 400,45" fill="#fff" stroke="{C_HIGH}" stroke-width="2"/>
  <text x="470" y="49" text-anchor="middle" font-size="13">Decision</text>
  <polygon points="600,20 710,20 690,70 580,70" fill="#eef0f4" stroke="{C_SDA}" stroke-width="2"/>
  <text x="645" y="49" text-anchor="middle" font-size="12">Input / output</text>
</svg>"""

MASTER_FLOW_SVG = f"""
<svg viewBox="0 0 640 470" class="g-svg" role="img" aria-label="End-to-end monitoring flow">
  <defs><marker id="ar" markerWidth="9" markerHeight="9" refX="7" refY="3" orient="auto">
    <path d="M0,0 L7,3 L0,6 Z" fill="{C_SDA}"/></marker></defs>
  <g font-size="12.5" text-anchor="middle">
  <polygon points="200,8 440,8 420,52 180,52" fill="#eef0f4" stroke="{C_SDA}" stroke-width="2"/>
  <text x="310" y="27">Data arrives — file / DB feed /</text>
  <text x="310" y="43">manual / scheduled (monthly)</text>
  <rect x="180" y="78" width="260" height="46" rx="6" fill="#fff" stroke="{C_SDA}" stroke-width="2"/>
  <text x="310" y="98">Validate against the data contract</text>
  <text x="310" y="114" fill="#888">malformed rows quarantined</text>
  <rect x="180" y="150" width="260" height="46" rx="6" fill="#fff" stroke="{C_SDA}" stroke-width="2"/>
  <text x="310" y="170">Model scores P(MIA3 slip)</text>
  <text x="310" y="186" fill="#888">+ SHAP explanation stored</text>
  <rect x="180" y="222" width="260" height="46" rx="6" fill="#fff" stroke="{C_SDA}" stroke-width="2"/>
  <text x="310" y="242">Risk score 0.5 / 0.3 / 0.2</text>
  <text x="310" y="258" fill="#888">→ four risk bands</text>
  <polygon points="310,290 430,330 310,370 190,330" fill="#fff" stroke="{C_HIGH}" stroke-width="2"/>
  <text x="310" y="334">Confidence routing</text>
  <rect x="120" y="398" width="130" height="42" rx="6" fill="#eaf2ff" stroke="{C_ACCENT}"/>
  <text x="185" y="423">Internal Risk</text>
  <rect x="262" y="398" width="116" height="42" rx="6" fill="#eaf2ff" stroke="{C_ACCENT}"/>
  <text x="320" y="423">Branch</text>
  <rect x="390" y="398" width="130" height="42" rx="6" fill="#eaf2ff" stroke="{C_ACCENT}"/>
  <text x="455" y="423">FI (own book)</text>
  </g>
  <g stroke="{C_SDA}" stroke-width="2" fill="none" marker-end="url(#ar)">
    <path d="M310,52 L310,76"/><path d="M310,124 L310,148"/>
    <path d="M310,196 L310,220"/><path d="M310,268 L310,288"/>
    <path d="M250,360 L200,396"/><path d="M310,370 L320,396"/><path d="M380,360 L440,396"/>
  </g>
</svg>"""

RISK_RULER_SVG = f"""
<svg viewBox="0 0 640 96" class="g-svg" role="img" aria-label="Risk band ruler">
  <g font-size="12">
  <rect x="40" y="30" width="200" height="26" fill="{C_LOW}"/>
  <rect x="240" y="30" width="200" height="26" fill="{C_MOD}"/>
  <rect x="440" y="30" width="100" height="26" fill="{C_HIGH}"/>
  <rect x="540" y="30" width="60"  height="26" fill="{C_VHIGH}"/>
  <text x="140" y="47" text-anchor="middle" fill="#fff">Low</text>
  <text x="340" y="47" text-anchor="middle">Moderate</text>
  <text x="490" y="47" text-anchor="middle" fill="#fff">High</text>
  <text x="570" y="47" text-anchor="middle" fill="#fff" font-size="10">V.High</text>
  <g fill="#444" text-anchor="middle">
    <text x="40" y="74">1.0</text><text x="240" y="74">2.0</text>
    <text x="440" y="74">3.0</text><text x="540" y="74">3.5</text><text x="600" y="74">4.0</text>
  </g>
  </g>
</svg>"""

ARITHMETIC_SVG = f"""
<svg viewBox="0 0 640 130" class="g-svg" role="img" aria-label="Risk score arithmetic">
  <g font-size="13" text-anchor="middle">
  <rect x="20"  y="20" width="180" height="56" rx="6" fill="#fff" stroke="{C_SDA}"/>
  <text x="110" y="42">0.50 × rank P(MIA3)</text><text x="110" y="62" fill="#888">most weight</text>
  <rect x="230" y="20" width="170" height="56" rx="6" fill="#fff" stroke="{C_SDA}"/>
  <text x="315" y="42">0.30 × rank EAD</text><text x="315" y="62" fill="#888">size of loss</text>
  <rect x="430" y="20" width="190" height="56" rx="6" fill="#fff" stroke="{C_SDA}"/>
  <text x="525" y="42">0.20 × rank Out-ratio</text><text x="525" y="62" fill="#888">leverage</text>
  <text x="210" y="55">+</text><text x="415" y="55">+</text>
  <text x="320" y="110" font-size="15" font-weight="700">= Risk score (1.0 – 4.0) → band</text>
  </g>
</svg>"""

ROUTING_SVG = f"""
<svg viewBox="0 0 640 210" class="g-svg" role="img" aria-label="Confidence routing">
  <defs><marker id="ar2" markerWidth="9" markerHeight="9" refX="7" refY="3" orient="auto">
    <path d="M0,0 L7,3 L0,6 Z" fill="{C_SDA}"/></marker></defs>
  <g font-size="12.5" text-anchor="middle">
  <polygon points="150,10 250,45 150,80 50,45" fill="#fff" stroke="{C_HIGH}" stroke-width="2"/>
  <text x="150" y="49">Confidence high?</text>
  <polygon points="150,120 250,155 150,190 50,155" fill="#fff" stroke="{C_HIGH}" stroke-width="2"/>
  <text x="150" y="159">High-risk band?</text>
  <rect x="430" y="22" width="180" height="46" rx="6" fill="#fff5e6" stroke="{C_HIGH}"/>
  <text x="520" y="42">Needs review</text><text x="520" y="58" fill="#888">borderline confidence</text>
  <rect x="430" y="100" width="180" height="40" rx="6" fill="#eef7ee" stroke="{C_LOW}"/>
  <text x="520" y="124">Fast-track to worklist</text>
  <rect x="430" y="156" width="180" height="40" rx="6" fill="#f3f4f6" stroke="#999"/>
  <text x="520" y="180">No review needed</text>
  </g>
  <g stroke="{C_SDA}" stroke-width="2" fill="none" marker-end="url(#ar2)">
    <path d="M150,80 L150,118"/>
    <path d="M250,45 L428,45"/>
    <path d="M250,150 L428,120"/>
    <path d="M250,160 L428,176"/>
  </g>
  <g font-size="11" fill="#666">
    <text x="330" y="38">No → review</text>
    <text x="335" y="138">Yes</text><text x="335" y="190">No</text>
    <text x="160" y="105">Yes</text>
  </g>
</svg>"""

DUAL_CONTROL_SVG = f"""
<svg viewBox="0 0 640 110" class="g-svg" role="img" aria-label="Dual control">
  <defs><marker id="ar3" markerWidth="9" markerHeight="9" refX="7" refY="3" orient="auto">
    <path d="M0,0 L7,3 L0,6 Z" fill="{C_SDA}"/></marker></defs>
  <g font-size="12.5" text-anchor="middle">
  <rect x="20" y="35" width="150" height="44" rx="6" fill="#fff" stroke="{C_SDA}"/>
  <text x="95" y="61">Maker proposes</text>
  <rect x="245" y="35" width="150" height="44" rx="6" fill="#fff5e6" stroke="{C_HIGH}"/>
  <text x="320" y="55">Preview re-banding</text><text x="320" y="71" fill="#888" font-size="10">before/after</text>
  <rect x="470" y="35" width="150" height="44" rx="6" fill="#eef7ee" stroke="{C_LOW}"/>
  <text x="545" y="55">Checker approves</text><text x="545" y="71" fill="#888" font-size="10">≠ maker</text>
  </g>
  <g stroke="{C_SDA}" stroke-width="2" fill="none" marker-end="url(#ar3)">
    <path d="M170,57 L243,57"/><path d="M395,57 L468,57"/>
  </g>
</svg>"""


def _steps(*items: str) -> str:
    return "<ol class='steps'>" + "".join(f"<li>{i}</li>" for i in items) + "</ol>"


def _note(text: str) -> str:
    return f"<div class='g-note'>{text}</div>"


def _warn(text: str) -> str:
    return f"<div class='g-warn'>{text}</div>"


def _seen(*items: str) -> str:
    head = "<p class='g-seen-h'>On this screen you will see</p>"
    return head + "<ul class='g-seen'>" + "".join(f"<li>{i}</li>" for i in items) + "</ul>"


# --- The sections ----------------------------------------------------------
SECTIONS: List[Dict[str, str]] = [
    {"id": "live-test", "num": "1", "title": "LIVE and TEST environments", "body": f"""
<p>The engine runs two ringfenced environments. Always check which one you are in
before acting — the colour of the top bar tells you instantly.</p>
<table><tr><th>Environment</th><th>What it is</th><th>Visual cue</th></tr>
<tr><td><span class="badge" style="background:#003A70">LIVE</span></td>
<td>Real monitoring. Only production models drive outcomes.</td><td>CGC-blue top bar, no watermark.</td></tr>
<tr><td><span class="badge" style="background:#FF8819;color:#3a2400">TEST</span></td>
<td>Ringfenced sandbox for demonstration and calibration trials. Separate
database and audit chain.</td><td>CGC-orange bar, <code>TEST — NOT LIVE DATA</code> watermark, <code>TEST-</code> run ids.</td></tr></table>
{_steps(
 "<b>Read the top bar.</b> Blue = LIVE, orange = TEST.",
 "<b>TEST is the default.</b> LIVE must be set deliberately by an administrator (MIA3_ENV=LIVE) — so LIVE is never reached by accident.",
 "<b>Test data never reaches LIVE.</b> The two environments have separate databases and audit chains.")}
{_warn("Nothing is published to the FI or branch views, deployed to LIVE, or sent to "
       "an FI without a person's go-ahead. While the model is in calibration, every "
       "high-risk flag is a prompt for human attention — never an automated action.")}"""},

    {"id": "help", "num": "2", "title": "In-app help and this guide", "body": f"""
<p>Guidance is delivered in four layers, present on every screen.</p>
<table><tr><th>Layer</th><th>What it is</th></tr>
<tr><td>Purpose banner</td><td>A plain-language statement at the top of each screen of what it is for.</td></tr>
<tr><td>Field tooltips</td><td>An <span class="info">i</span> icon on every data-entry field explaining what it means.</td></tr>
<tr><td>Guided / compact modes</td><td>New users get all help visible; experienced users hide it — a per-user toggle in the header.</td></tr>
<tr><td>This user guide</td><td>A context-sensitive manual reachable from every screen.</td></tr></table>
{_steps(
 "<b>Open contextual help</b> by clicking <b>📖 User guide</b> in a screen's purpose banner — it opens this guide at the section for that screen.",
 "<b>Open the full guide</b> any time from the <b>📖 Guide</b> link in the top navigation, or the <b>?</b> button.",
 "<b>Hover the <span class='info'>i</span> icons</b> on any form field for a tooltip. <b>Jump between topics</b> using the index on the left.")}"""},

    {"id": "flow", "num": "3", "title": "The end-to-end monitoring flow", "body": f"""
<p>MIA3 is a <b>smoke detector</b>: it watches loans already on the book and raises
an alarm when one starts to smoulder. Every scoring cycle follows the same fixed
order, shown below. (Flowchart symbols used throughout this guide:)</p>
{SYMBOLS_SVG}
{MASTER_FLOW_SVG}
{_note("Lineage is written to the append-only, hash-chained audit store at every "
       "stage, so any score is fully reconstructable (see §16). The SHAP explanation "
       "is computed and stored during the scoring run, so the dashboards open instantly.")}"""},

    {"id": "dashboard", "num": "4", "title": "Portfolio overview (the radar)", "body": f"""
<p>The dashboard turns thousands of scored accounts into something you can read at a
glance. It always reflects the latest <i>published</i> run.</p>
{_seen(
 "A <b>What's shaping the risk picture</b> panel — the active model(s) and Decision Rule per segment, so you always know what produced the numbers.",
 "Four <b>band cards</b> — counts of Very High, High, Moderate and Low risk. Click a card to see those accounts.",
 "A <b>risk-band mix</b> donut and an <b>exposure-by-band</b> bar — counts and the RM at risk side by side (a few Very-High accounts often hold most of the money).",
 "A <b>risk map</b> — every account plotted by probability against exposure; the shaded top-right quadrant (likely <i>and</i> high-impact) is where to act first.",
 "<b>By-FI / scheme / sector band heatmaps</b> — cell shading shows where each band concentrates, and a <b>trend</b> stacked-area shows deterioration as a shape over runs.",
 "<b>By FI, by scheme and by sector</b> tables, each sortable, with the high-risk share highlighted.",
 "A <b>trend</b> table — how each band's population moves run to run, so deterioration shows as a shape.",
 "Any <b>portfolio early-warning ladder</b> alerts for the run (see §14).")}
{_steps(
 "Scan the band cards for the overall shape of risk.",
 "Use the by-FI / by-sector tables to find <i>where</i> risk is concentrating — a red high-share cell is a place to look.",
 "Click any total to drill straight into the accounts behind it, then into a single account's explanation (§6).")}
{_note("FI users see only their own book here; branch and internal users see the whole portfolio.")}"""},

    {"id": "accounts", "num": "5", "title": "Accounts and the worklist", "body": f"""
<p>The accounts screen lists every scored account in the latest run, highest risk
first. The <b>worklist</b> is the same list filtered to what needs attention.</p>
{_seen(
 "A row per account with P(MIA3), EAD, risk score, band, confidence and routing.",
 "Filters for band, scheme and sector (FI users are automatically scoped to their book).",
 "A <b>routing</b> tag: <i>fast-track</i>, <i>needs review</i> or <i>no review</i>.")}
{_steps(
 "Filter or sort to the slice you care about.",
 "Open any account id to see why it was flagged and how its band was reached (§6).",
 "Branch users: start from the <b>Worklist</b> — it shows only fast-track and needs-review accounts.")}"""},

    {"id": "account", "num": "6", "title": "Reading an account", "body": f"""
<p>The account detail page explains one account two ways, and lets you act on it.</p>
{_seen(
 "<b>How the band was reached</b> — the full 0.5 / 0.3 / 0.2 arithmetic, live (decision explainability).",
 "<b>Why the model flagged it</b> — the top SHAP factors, each shown pushing risk up (red) or down (green).",
 "A <b>confidence</b> breakdown across its five components, and the routing decision.",
 "A <b>Download case report (.docx)</b> button, and a <b>review decision</b> form.")}
{_steps(
 "Read the arithmetic table — it is the deck's worked example, generated for this account.",
 "Read the SHAP factors to understand the drivers; expand the technical view if you are a validator.",
 "Optionally run the <b>LIME challenger</b> (a second, diagnostic read) from the link.",
 "Download a one-page <b>case report</b> to attach to a file or take to a committee.",
 "If you are internal/branch, record a review decision (§9).")}
{_note("Explanations are read from the stored decision record, never recomputed against "
       "today's model — so an explanation always reflects the score as it was actually made.")}"""},

    {"id": "riskscore", "num": "7", "title": "The risk score and the four bands", "body": f"""
<p>The risk score combines three ranked components. Probability carries the most
weight because it reflects how likely the account is to turn non-performing;
exposure and leverage scale that by how much is at stake.</p>
{ARITHMETIC_SVG}
<p>Each component is ranked 1–4 (low→high risk), then the score maps to a band:</p>
{RISK_RULER_SVG}
<table><tr><th>Band</th><th>Score</th><th>Meaning</th></tr>
<tr><td><span class="badge" style="background:{C_VHIGH}">Very High</span></td><td>&gt; 3.5</td><td>Very likely to cause significant loss; immediate action.</td></tr>
<tr><td><span class="badge" style="background:{C_HIGH}">High</span></td><td>3.0 – 3.5</td><td>Likely to cause loss with noticeable impact.</td></tr>
<tr><td><span class="badge" style="background:{C_MOD}">Moderate</span></td><td>2.0 – 3.0</td><td>Early signs of risk, still manageable.</td></tr>
<tr><td><span class="badge" style="background:{C_LOW}">Low</span></td><td>&lt; 2.0</td><td>Financially stable.</td></tr></table>
{_note("The weights and band cut-offs are governed settings, not hardcoded numbers — "
       "they are changed through the dual-control workflow in §12, never in code.")}"""},

    {"id": "confidence", "num": "8", "title": "Confidence and review routing", "body": f"""
<p>Every prediction carries a confidence score (0–100), not just a risk score.
It is a weighted blend of five components:</p>
<table><tr><th>Component</th><th>Weight</th></tr>
<tr><td>Model performance (back-tested)</td><td>35%</td></tr>
<tr><td>Data completeness (were inputs present, not defaulted?)</td><td>25%</td></tr>
<tr><td>Data quality (clean / in range?)</td><td>20%</td></tr>
<tr><td>Population fit (how typical is this account?)</td><td>10%</td></tr>
<tr><td>Calibration (is the active model calibrated?)</td><td>10%</td></tr></table>
<p>Confidence drives where scarce human attention goes:</p>
{ROUTING_SVG}
{_warn("This is the direct answer to the precision caution: in recent monthly results "
       "precision is very low (around 0.1), so roughly nine in ten flags are false "
       "alarms. The confidence gate and mandatory human review are what stop those false "
       "alarms from becoming wasted effort or unfair treatment of a customer.")}"""},

    {"id": "review", "num": "9", "title": "The human review queue", "body": f"""
<p>Borderline-confidence and elevated-risk accounts wait in the review queue for a
person to confirm or dismiss the machine's call before any action follows.</p>
{_seen(
 "A prioritised list of accounts whose routing is <i>needs review</i>.",
 "On each account, a decision form: <b>Confirm</b>, <b>Override</b> or <b>Escalate</b>, with a reason and an optional observed outcome.")}
{_steps(
 "Open an account from the queue and read its explanation (§6).",
 "Record your decision. A <b>reason is required to override</b>.",
 "Optionally record the <b>observed outcome</b> — it feeds the learnings evidence base for re-calibration (§15).")}
{_note("A human override changes the treatment, never the model's number — the machine's "
       "estimate and your decision are recorded as two distinct facts.")}"""},

    {"id": "runs", "num": "10", "title": "Running a scoring cycle", "body": f"""
<p>Internal-risk users run scoring cycles from the <b>Runs</b> screen. A dropped file
is the default; a live database feed and a scheduled monthly run are the alternatives.</p>
{_seen(
 "An <b>upload</b> form (CSV or JSON) with a <i>hold for sign-off</i> checkpoint option.",
 "A table of past runs with the model version, row counts and a <b>data-quality report</b> (accepted / quarantined / acceptance %).",
 "A <b>Publish</b> action on any run that is held.")}
{_steps(
 "Drop the monthly file. It is validated against the data contract (§11) before anything is scored.",
 "Malformed rows are quarantined and counted; the rest score normally.",
 "If you ticked <i>hold</i> — or if acceptance falls below 75% — the run is held; review the quality report and <b>Publish</b> when satisfied.")}
{_warn("Scheduled runs on the hosted TEST app are triggered manually or via the Runs "
       "page. Publishing pushes results to the branch and FI views — do it deliberately.")}"""},

    {"id": "contract", "num": "11", "title": "The data contract", "body": f"""
<p>The data contract is the exact schema the monthly file must follow. The
<b>Data contract</b> screen lists every column, its type, whether it is required,
and how a missing value is handled.</p>
{_seen(
 "Three groups: <b>identity &amp; roll-up</b> (account, FI, scheme, sector), <b>risk-score inputs</b> (EAD, outstanding ratio), and <b>model features</b>.",
 "Per column: type, required?, on-missing behaviour, default, valid range.")}
<table><tr><th>On missing</th><th>What happens</th></tr>
<tr><td><code>reject</code></td><td>The row is quarantined — it cannot be scored safely.</td></tr>
<tr><td><code>default</code></td><td>The value is filled with the documented default and the account's confidence is reduced.</td></tr></table>
{_note("FIs can fetch the machine-readable contract at <code>/api/v1/contract</code> to "
       "build their file against it.")}"""},

    {"id": "tuning", "num": "12", "title": "Tuning thresholds and calibration", "body": f"""
<p>Internal-risk users adjust the 50/30/20 weights, the band cut-offs, and the model
calibration on the <b>Tuning</b> screen. Nothing changes on one person's say-so.</p>
{DUAL_CONTROL_SVG}
{_seen(
 "The currently active weights and band cut-offs.",
 "A propose form with a <b>preview</b> of how the latest portfolio re-bands under the new settings.",
 "A queue of proposed changes awaiting a second approver, and the calibration controls.")}
{_steps(
 "Enter new weights (they must sum to 1.00) and/or band cut-offs.",
 "Click <b>Preview re-banding</b> to see exactly how many accounts move band — tuning is never a leap in the dark.",
 "<b>Submit the proposal.</b> A different person must approve it — the proposer cannot approve their own change.",
 "For calibration, choose a method (identity / linear / platt), set its parameters, add a note, and propose. Defaults to uncalibrated so nothing changes silently.")}
{_warn("Every change is versioned, reasoned, time-stamped and reversible, and recorded on "
       "the audit trail with its before/after values.")}"""},

    {"id": "models", "num": "13", "title": "The model registry", "body": f"""
<p>The <b>Models</b> screen is where internal-risk users register, edit, swap and
retire decision models. Several model <b>types</b> are supported, and <b>more than one
model can be active per segment</b>; how they combine into the trigger is set by a
<b>Decision Rule</b> (§13c). The scoring engine only ever uses <b>active</b> models — never a draft.</p>
<table><tr><th>Model type</th><th>What it is</th></tr>
<tr><td>Synthetic</td><td>The built-in deterministic stand-in.</td></tr>
<tr><td>Logistic regression</td><td>A glass-box model you define in-app by a coefficient spec; probability = sigmoid(intercept + Σ weight·feature).</td></tr>
<tr><td>OLS / linear regression</td><td>A glass-box linear model defined the same way; output clipped to 0–1.</td></tr>
<tr><td>ML artifact (XGBoost / sklearn)</td><td>An uploaded trained artifact, validated against the data contract.</td></tr></table>
{DUAL_CONTROL_SVG}
{_seen(
 "The <b>live model</b> card — the active version, its metrics, and a <b>Retire</b> button.",
 "A <b>Register a new model</b> form — name, version, kind, an artifact upload (or server path), back-test metrics and notes.",
 "The registry table with each version's status (draft / active / retired), an <b>artifact validity</b> check, and <b>Activate</b> / <b>Edit</b> actions.")}
{_steps(
 "<b>Register</b> a new version. Upload its .json/.ubj/.pkl artifact (or give a path), or choose <i>synthetic</i> for a stand-in. It is saved as a <b>draft</b>.",
 "The registry shows an <b>artifact check</b> — ✓ valid means it loaded and its features match the data contract; ✗ invalid shows why.",
 "A <b>different</b> internal-risk user clicks <b>Activate</b> (dual control — the registrant cannot activate their own). The artifact is re-validated, the previous model is retired, and the next scoring run uses the new one.",
 "<b>Edit</b> a draft or retired entry's metadata (retire the live model first to edit it). <b>Retire</b> the live model any time — scoring falls back to the synthetic stand-in.")}
{_note("The real back-tested XGBoost artifact can also be supplied at deploy time via "
       "the MIA3_MODEL_PATH setting. Either way, the loader refuses an artifact whose "
       "features do not match the data contract, so a mismatched model can never score.")}"""},

    {"id": "rules", "num": "13a", "title": "Decision rules (ensembles)", "body": f"""
<p>When more than one model is active for a segment, the early-warning trigger is an
<b>ensemble</b> — the combination defined by the segment's active <b>Decision Rule</b>.
Rules are governed exactly like models: a maker proposes, a different checker approves.</p>
{DUAL_CONTROL_SVG}
<table><tr><th>Method</th><th>How models combine</th></tr>
<tr><td>single</td><td>Use one model only (the default when just one is active).</td></tr>
<tr><td>average</td><td>Mean of the models' probabilities.</td></tr>
<tr><td>weighted</td><td>Weighted mean (weights by model version).</td></tr>
<tr><td>max</td><td>Most conservative — flags if any model is high.</td></tr>
<tr><td>min / median</td><td>Least conservative / robust middle.</td></tr>
<tr><td>majority</td><td>Share of models whose probability ≥ the rule threshold.</td></tr></table>
{_steps(
 "Activate the models you want in the ensemble on the Models screen (§13).",
 "On <b>Decision rules</b>, choose the segment and method (and weights or threshold), and submit.",
 "A different approver activates it; the next scoring run uses the new combination.",
 "Deactivate any time — the segment reverts to the default (single model, or an average of several).")}
{_note("Each segment has exactly one active rule. The dashboard always shows which "
       "models and which rule are shaping the picture (§4).")}"""},

    {"id": "performance", "num": "13b", "title": "Model performance monitoring", "body": f"""
<p>Once realised MIA 3 outcomes are recorded, the <b>Performance</b> screen tracks how the
model actually did, per run and segment, against the go-live goals from the deck:
<b>Recall &gt; 75%</b>, <b>AUC &gt; 65%</b>, <b>false-negative rate &lt; 20%</b>.</p>
{_seen(
 "A row per run and segment with Recall, Precision, FN rate and AUC, each coloured against its goal.",
 "An overall <b>all met / below goal</b> badge per row.",
 "An <b>Intervened</b> share — the selective-labels caveat (outcomes influenced by an action taken).")}
{_steps(
 "Record realised outcomes on accounts (the ‘Record realised outcome’ form on an account), as accounts mature.",
 "In TEST, use <b>Simulate outcomes for latest run</b> to populate the view with a realistic synthetic set.",
 "Read the metrics against the goals; a high intervention rate means treat the numbers as optimistic.")}
{_warn("Outcomes where an intervention was applied are biased — the action, not just the "
       "borrower, shaped the result. This is recorded so future re-calibration can correct "
       "for it (the selective-labels problem). Reject inference does not apply to MIA3 — it "
       "scores the existing book, not applicants it never observes.")}"""},

    {"id": "ladder", "num": "14", "title": "Portfolio early-warning ladder", "body": f"""
<p>Beyond per-account flags, MIA3 watches concentrations. When the share of an FI's or
a sector's book in the high-risk bands crosses a governed level, it raises a
portfolio-level alert on the dashboard.</p>
<table><tr><th>Tripwire</th><th>High-risk share</th><th>Meaning</th></tr>
<tr><td><span class="badge" style="background:{C_HIGH}">Watch</span></td><td>≥ 15%</td><td>Review this FI / sector concentration.</td></tr>
<tr><td><span class="badge" style="background:{C_VHIGH}">Halt</span></td><td>≥ 30%</td><td>Escalate — concentration is severe.</td></tr></table>
{_note("Groups smaller than five accounts are ignored as too small to be meaningful.")}"""},

    {"id": "learnings", "num": "15", "title": "The learnings library", "body": f"""
<p>The Learnings Library is the reference home for the engine, and the record of what the
institution learns as the model runs — turning a tool that scores into one that improves.</p>
{_seen(
 "<b>Documentation &amp; references</b> — open or download the Quick Start and User Guide, the data contract and the API reference.",
 "<b>Key concepts</b> cards — short explainers (what MIA3 is, the risk score and bands, confidence, governance) each linking to the relevant guide section.",
 "<b>FAQs</b> — the common questions answered in one place.",
 "<b>Field learnings &amp; outcomes</b> — a form and feed to record which flags proved right, reviewer notes, and the reasoning behind model/threshold changes.")}
{_steps(
 "Use the documentation cards to onboard a new user or share a guide.",
 "Record outcomes as accounts mature: which flagged accounts genuinely deteriorated and which did not.",
 "Capture reviewer notes, recurring patterns, and the reasoning behind every governed change — so the story of the model is never lost and re-calibration has an evidence base.")}"""},

    {"id": "audit", "num": "16", "title": "The audit trail", "body": f"""
<p>The <b>Audit</b> screen is the tamper-evident record of everything the system did
and who told it to. It is append-only and read-only here.</p>
{_seen(
 "An integrity banner — the chain is re-verified on every view.",
 "A timestamped, attributed event list: every scoring run, threshold/calibration change, model activation, review decision and login.",
 "A short hash on each row; entries are linked by SHA-256 so any later edit breaks the chain and is detectable.")}
{_note("For a regulated guarantee institution this turns 'trust us' into 'here is the "
       "evidence, tested'. The log is exportable for an auditor.")}"""},

    {"id": "demo", "num": "17", "title": "Demonstration mode", "body": f"""
<p>Demonstration mode is a ringfenced, synthetic sandbox that exercises every feature
and edge case — so you can show the platform to a committee or an FI without touching
real data.</p>
{_steps(
 "Open <b>Demo</b> and click <b>Generate &amp; score demo portfolio</b>.",
 "It creates ~400 synthetic accounts across all four bands, several FIs, schemes and sectors,",
 "plus deliberate boundary cases: a band-edge account, high-probability/low-exposure, low-probability/high-exposure, a borderline-confidence case that routes to review, and a malformed row that is quarantined.",
 "Explore the dashboard, accounts and review queue as normal.")}
{_warn("Demonstration data is synthetic and clearly flagged. No real borrower data is "
       "ever used in development or testing.")}"""},

    {"id": "glossary", "num": "18", "title": "Glossary and risk bands", "body": f"""
<table><tr><th>Term</th><th>Meaning</th></tr>
<tr><td>MIA 3</td><td>Months-in-Arrears 3 — the deterioration event the model predicts.</td></tr>
<tr><td>P(MIA3 slip)</td><td>The model's probability an account reaches MIA 3 in the forecast horizon.</td></tr>
<tr><td>EAD</td><td>Exposure at Default — RM amount at risk if the account defaults.</td></tr>
<tr><td>Outstanding ratio</td><td>Outstanding / utilisation — a customer-leverage signal.</td></tr>
<tr><td>Risk score</td><td>0.5·rank P(MIA3) + 0.3·rank EAD + 0.2·rank Outstanding ratio (range 1.0–4.0).</td></tr>
<tr><td>Confidence</td><td>0–100 trust in a prediction; five-component blend (§8).</td></tr>
<tr><td>Calibration</td><td>A governed mapping of raw model output onto observed reality.</td></tr>
<tr><td>Quarantine</td><td>A row that cannot be scored safely; set aside, never guessed.</td></tr>
<tr><td>SHAP / LIME</td><td>SHAP is the official, stored explanation; LIME is an on-demand diagnostic challenger.</td></tr></table>
{RISK_RULER_SVG}"""},
]

SECTION_IDS = [s["id"] for s in SECTIONS]
SECTION_BY_ID: Dict[str, Dict[str, str]] = {s["id"]: s for s in SECTIONS}

# Map each app screen to the guide section that explains it.
SCREEN_TO_SECTION: Dict[str, str] = {
    "dashboard": "dashboard", "accounts": "accounts", "account_detail": "account",
    "worklist": "review", "review": "review", "runs": "runs", "tuning": "tuning",
    "demo": "demo", "learnings": "learnings", "audit": "audit", "models": "models",
    "contract": "contract", "login": "live-test", "performance": "performance",
    "rules": "rules",
}


def section_for_screen(screen: Optional[str]) -> str:
    """The guide anchor a given screen's contextual help link should open."""
    if not screen:
        return SECTION_IDS[0]
    return SCREEN_TO_SECTION.get(screen, SECTION_IDS[0])


def toc() -> List[Dict[str, str]]:
    return [{"id": s["id"], "num": s["num"], "title": s["title"]} for s in SECTIONS]
