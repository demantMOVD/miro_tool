"""
Team Timeline – Streamlit App
Run with:  streamlit run app.py
"""
import io
import os
import streamlit as st
from data import (
    load, save_full, get_iterations, get_task, set_task,
    get_team_task_sp_sum, get_all_features,
    get_slot_count, get_next_slot,
    TEAM_OWNER, DEFAULT_DATA
)
from generate_timeline import generate as gen_excel

# ─────────────────────────────────────────────────────────────────────────────
#  PAGE CONFIG
# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Team Timeline",
    page_icon="🗓",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────────────────────────────────────────
#  CUSTOM CSS
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
/* General */
html, body, [class*="css"] { font-family: 'Segoe UI', sans-serif; }

/* Sidebar */
section[data-testid="stSidebar"] { background: #1F3864; color: white; }
section[data-testid="stSidebar"] * { color: white !important; }
section[data-testid="stSidebar"] input,
section[data-testid="stSidebar"] textarea { color: #1F3864 !important; background: white !important; }

/* Timeline grid table */
.tl-table { border-collapse: collapse; width: 100%; table-layout: fixed; }
.tl-table th, .tl-table td { border: 1px solid #c0cfe0; padding: 4px 6px; vertical-align: top; }

/* Row-label cells */
.row-team  { background: #2E75B6; color: white; font-weight: bold; min-width: 110px; }
.row-member{ background: #BDD7EE; color: #1F3864; font-weight: bold; min-width: 110px; }

/* Iteration header */
.iter-header { background: #2E75B6; color: white; text-align: center; font-weight: bold; }
.month-header{ background: #2F5496; color: white; text-align: center; font-weight: bold; }
.date-sub    { background: #EBF3FB; color: #595959; text-align: center; font-size: 0.75em; }

/* Task cards */
.task-card {
    background: #FFF2CC;
    border: 1px solid #BF9000;
    border-radius: 6px;
    padding: 6px 8px;
    font-size: 0.78em;
    line-height: 1.5;
    cursor: pointer;
    min-height: 80px;
    word-break: break-word;
    color: #000000;
}
.task-card:hover { border-color: #2E75B6; box-shadow: 0 1px 6px #2E75B644; }
.task-empty {
    background: #F4F8FD;
    border: 1px dashed #ADC8E0;
    border-radius: 6px;
    padding: 6px 8px;
    font-size: 0.75em;
    color: #999;
    min-height: 80px;
    text-align: center;
    line-height: 5;
    cursor: pointer;
}
.task-team-badge {
    background: #2E75B6;
    color: white !important;
    border-radius: 4px;
    padding: 1px 5px;
    font-size: 0.7em;
    font-weight: bold;
    margin-bottom: 3px;
    display: inline-block;
}
.field-label { color: #7B6100; font-weight: bold; }
.sp-badge {
    display: inline-block;
    background: #1F3864;
    color: white !important;
    border-radius: 50%;
    width: 20px; height: 20px;
    text-align: center; line-height: 20px;
    font-size: 0.75em;
    font-weight: bold;
    float: right;
}

/* Horizontal scroll wrapper for the timeline */
.tl-scroll-outer {
    overflow-x: auto;
    overflow-y: visible;
    width: 100%;
    padding-bottom: 12px;
}
.tl-scroll-inner {
    min-width: max-content;
}
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
#  SESSION STATE
# ─────────────────────────────────────────────────────────────────────────────
if "data" not in st.session_state:
    st.session_state.data = load()

if "edit" not in st.session_state:
    st.session_state.edit = None

# ── Check secrets are configured when running on Streamlit Cloud ──────────
_on_cloud = os.environ.get("STREAMLIT_SHARING_MODE") or os.environ.get("IS_STREAMLIT_CLOUD")
_has_local_file = os.path.exists(os.path.join(os.path.dirname(os.path.abspath(__file__)), "timeline_data.json"))
_has_secrets = False
try:
    _has_secrets = bool(st.secrets.get("gist", {}).get("token"))
except Exception:
    pass

if not _has_secrets and not _has_local_file:
    st.error("⚠️ **No data storage configured.**")
    st.markdown("""
The app needs either:

**On Streamlit Cloud** — add these secrets in your app's **Settings → Secrets**:

```
[gist]
token   = "<your GitHub PAT with gist scope>"
gist_id = "<your Gist ID>"
```

**Running locally** — create `.streamlit/secrets.toml` with the same content,
or just run the app once and a local `timeline_data.json` will be created automatically.
    """)
    st.stop()

# Re-read from disk on every render UNLESS we are processing a form submission
if st.session_state.get("_form_submitting", False):
    st.session_state._form_submitting = False
    data = st.session_state.data
else:
    data = load()
    st.session_state.data = data

# Compute iterations early so they're available everywhere (including edit dialog)
try:
    iterations = get_iterations(data["start_date"], data["num_iterations"])
except Exception as ex:
    st.error(f"Invalid start date format. Use YYYY-MM-DD. ({ex})")
    st.stop()


# ─────────────────────────────────────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────────────────────────────────────
def persist():
    save_full(data)
    st.session_state.data = data


def open_edit(owner, iter_num, slot):
    st.session_state.edit = {"owner": owner, "iter_num": iter_num, "slot": slot}


def close_edit():
    st.session_state.edit = None


# ── Feature → colour map ──────────────────────────────────────────────────────
# Distinct soft background colours for feature cards (bg, border, text)
FEATURE_PALETTE = [
    ("#FFF2CC", "#BF9000", "#000"),   # yellow  (default)
    ("#E2EFDA", "#538135", "#000"),   # green
    ("#FCE4D6", "#C55A11", "#000"),   # orange
    ("#DDEBF7", "#2E75B6", "#000"),   # blue
    ("#E8D5F5", "#7030A0", "#000"),   # purple
    ("#FCE4EC", "#C0143C", "#000"),   # pink
    ("#E0F7FA", "#00838F", "#000"),   # teal
    ("#FFF9C4", "#F57F17", "#000"),   # amber
    ("#F3E5F5", "#6A1B9A", "#000"),   # deep purple
    ("#E8F5E9", "#2E7D32", "#000"),   # deep green
]


def feature_colours(feature_name: str) -> tuple[str, str, str]:
    """Return (bg, border, text) for a given feature name — same name always same colour."""
    if not feature_name.strip():
        return FEATURE_PALETTE[0]
    idx = hash(feature_name.strip().lower()) % len(FEATURE_PALETTE)
    return FEATURE_PALETTE[idx]


# ─────────────────────────────────────────────────────────────────────────────
#  SIDEBAR – CONFIG
# ─────────────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🗓 Timeline Config")
    st.divider()

    def _save_config():
        # on_change fires after session_state is updated — read new values from there
        data["project_name"]   = st.session_state.cfg_project_name
        data["team_name"]      = st.session_state.cfg_team_name
        data["start_date"]     = st.session_state.cfg_start_date
        data["num_iterations"] = st.session_state.cfg_num_iterations
        members_raw = st.session_state.get("cfg_members", "\n".join(data["members"]))
        new_m = [m.strip() for m in members_raw.splitlines() if m.strip()]
        if new_m:
            data["members"] = new_m
        save_full(data)
        st.session_state.data = data

    data["project_name"] = st.text_input("Project Name", value=data["project_name"],
                                          on_change=_save_config, key="cfg_project_name")
    data["team_name"]    = st.text_input("Team Name",    value=data["team_name"],
                                          on_change=_save_config, key="cfg_team_name")

    st.markdown("**Timeline Span**")
    c1, c2 = st.columns(2)
    with c1:
        data["start_date"] = st.text_input("Start date (YYYY-MM-DD)", value=data["start_date"],
                                            on_change=_save_config, key="cfg_start_date")
    with c2:
        data["num_iterations"] = st.number_input("Number of iterations", min_value=1, max_value=52,
                                                  value=data["num_iterations"], step=1,
                                                  on_change=_save_config, key="cfg_num_iterations")

    st.markdown("**Team Members**")
    raw = st.text_area(
        "One name per line",
        value="\n".join(data["members"]),
        height=130,
        on_change=_save_config,
        key="cfg_members",
    )
    new_members = [m.strip() for m in raw.splitlines() if m.strip()]
    if new_members != data["members"]:
        data["members"] = new_members

    if st.button("💾 Save Config", use_container_width=True):
        persist()
        st.success("Saved!")

    st.divider()

    # ── Excel export ──────────────────────────────────────────────────────────
    st.markdown("**Export**")
    if st.button("📥 Generate Excel", use_container_width=True):
        with st.spinner("Building Excel…"):
            out = io.BytesIO()
            import tempfile, os
            with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tf:
                tmp = tf.name
            gen_excel(
                project_name=data["project_name"],
                team_name=data["team_name"],
                start_month=data["start_date"][:7],   # YYYY-MM
                num_months=max(1, data["num_iterations"] // 2),
                members=data["members"],
                output_file=tmp,
            )
            with open(tmp, "rb") as f:
                out.write(f.read())
            os.remove(tmp)
        st.download_button(
            "⬇️ Download .xlsx",
            data=out.getvalue(),
            file_name="TeamTimeline.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )

    st.divider()

    # ── Danger Zone ───────────────────────────────────────────────────────────
    st.markdown("**⚠️ Danger Zone**")

    if "reset_confirmed" not in st.session_state:
        st.session_state.reset_confirmed = False

    confirmed = st.checkbox("I know what I'm doing",
                            value=st.session_state.reset_confirmed,
                            key="reset_confirm_widget")
    st.session_state.reset_confirmed = confirmed

    if st.button("🗑 Clear all tasks", use_container_width=True,
                 disabled=not confirmed):
        data["tasks"] = {}
        save_full(data)
        st.session_state.data = data
        st.session_state.reset_confirmed = False
        st.session_state._form_submitting = True
        st.rerun()

    if st.button("↺ Full reset to defaults", use_container_width=True,
                 disabled=not confirmed):
        fresh = dict(DEFAULT_DATA)
        save_full(fresh)
        st.session_state.data = fresh
        st.session_state.reset_confirmed = False
        st.session_state._form_submitting = True
        st.rerun()

    st.divider()
    st.caption("Iterations = 2-week blocks (constant)")


# ─────────────────────────────────────────────────────────────────────────────
#  TASK EDIT DIALOG
# ─────────────────────────────────────────────────────────────────────────────
if st.session_state.edit is not None:
    e = st.session_state.edit
    owner    = e["owner"]
    iter_num = e["iter_num"]
    slot     = e["slot"]
    task     = get_task(data, owner, iter_num, slot)

    display_owner       = "Team" if owner == TEAM_OWNER else owner
    is_team_task        = (owner == TEAM_OWNER)
    is_member_team_slot = (owner != TEAM_OWNER and slot == 0)

    with st.expander(
        f"✏️  Editing task — **{display_owner}** · Iter {iter_num} · Slot {slot + 1}",
        expanded=True
    ):
        with st.form(key="task_form"):
            if is_member_team_slot:
                st.info("📌 This is the **team task** for this iteration. You can set your own **SP estimate** for it below — it will be summed into the team total shown on the team row.")

            # For member-team-slot, pull content from the actual team task
            display_task = get_task(data, TEAM_OWNER, iter_num, 0) if is_member_team_slot else task

            feature = st.text_input("FEATURE – feature / epic name",
                                    value=display_task.get("feature", ""),
                                    disabled=is_member_team_slot)
            descr   = st.text_area("DESCR – what needs to be done",
                                   value=display_task.get("descr", ""), height=80,
                                   disabled=is_member_team_slot)
            ac      = st.text_area("AC – acceptance criterion",
                                   value=display_task.get("ac", ""), height=80,
                                   disabled=is_member_team_slot)
            c1, c2  = st.columns(2)
            with c1:
                if is_team_task:
                    sp_total = get_team_task_sp_sum(data, iter_num)
                    st.caption(f"SP is summed from member estimates: **{sp_total}**")
                    sp = ""
                else:
                    sp_options = ["", "1", "2", "3", "5", "8", "13", "21"]
                    current_sp = str(task.get("sp", ""))
                    sp_index   = sp_options.index(current_sp) if current_sp in sp_options else 0
                    sp = st.selectbox("SP – story points", options=sp_options, index=sp_index)
            with c2:
                if is_member_team_slot:
                    st.text_input("ITER", value=str(iter_num), disabled=True)
                    new_iter_num = iter_num
                else:
                    all_iter_nums = [it["num"] for it in iterations]
                    new_iter_num = st.selectbox(
                        "ITER – move to iteration",
                        options=all_iter_nums,
                        index=all_iter_nums.index(iter_num),
                        format_func=lambda n: f"Iter {n}  ({next(it['date_range'] for it in iterations if it['num'] == n)})"
                    )

            col_save, col_del, col_cancel = st.columns(3)
            with col_save:
                saved = st.form_submit_button("💾 Save", use_container_width=True,
                                              type="primary")
            with col_del:
                deleted = st.form_submit_button("🗑 Delete", use_container_width=True)
            with col_cancel:
                cancelled = st.form_submit_button("✖ Cancel", use_container_width=True)

            # ── Handle actions inside the form context ────────────────────────
            if saved:
                if is_member_team_slot:
                    # Only SP is editable for member team-slot copies
                    existing = get_task(data, owner, iter_num, slot)
                    existing["sp"] = sp
                    set_task(data, owner, iter_num, slot, existing)
                else:
                    new_task = {"feature": feature, "descr": descr, "ac": ac,
                                "sp": sp, "iter": new_iter_num}
                    if new_iter_num != iter_num:
                        # Remove from current slot
                        set_task(data, owner, iter_num, slot, {})
                        # Place in next free slot of the target iteration
                        target_slot = get_next_slot(data, owner, new_iter_num)
                        set_task(data, owner, new_iter_num, target_slot, new_task)
                    else:
                        set_task(data, owner, iter_num, slot, new_task)
                persist()
                close_edit()
                st.session_state._form_submitting = True
                st.rerun()

            if deleted:
                set_task(data, owner, iter_num, slot, {})
                persist()
                close_edit()
                st.session_state._form_submitting = True
                st.rerun()

            if cancelled:
                close_edit()
                st.session_state._form_submitting = True
                st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
#  MAIN AREA – HEADER
# ─────────────────────────────────────────────────────────────────────────────
st.markdown(
    f"<h1 style='color:#1F3864;margin-bottom:0'>🗓 {data['project_name']}"
    f"<span style='font-size:0.55em;color:#2E75B6;margin-left:16px'>{data['team_name']}</span></h1>",
    unsafe_allow_html=True
)

st.caption(f"{len(iterations)} iterations · {len(data['members'])} team members")
st.divider()


# ─────────────────────────────────────────────────────────────────────────────
#  FILTER BAR
# ─────────────────────────────────────────────────────────────────────────────
fc1, fc2, fc3 = st.columns([2, 2, 2])
with fc1:
    filter_member = st.selectbox(
        "👤 Show member",
        options=["All members"] + data["members"],
        index=0,
    )
with fc2:
    iter_options = ["All iterations"] + [f"Iter {it['num']}" for it in iterations]
    filter_iter  = st.selectbox("🔁 Jump to iteration", options=iter_options, index=0)
with fc3:
    known_features = get_all_features(data)
    filter_feature = st.selectbox(
        "🎨 Filter by feature",
        options=["All features"] + known_features,
        index=0,
    )

st.markdown("<br>", unsafe_allow_html=True)

# Determine which iterations to show
if filter_iter != "All iterations":
    show_iter_num = int(filter_iter.split(" ")[1])
    vis_iterations = [it for it in iterations if it["num"] == show_iter_num]
else:
    vis_iterations = iterations

# Determine which members to show
vis_members = (
    [m for m in data["members"] if m == filter_member]
    if filter_member != "All members"
    else data["members"]
)

feature_filter = "" if filter_feature == "All features" else filter_feature.strip().lower()


# ─────────────────────────────────────────────────────────────────────────────
#  TIMELINE GRID  –  pure HTML table inside a scroll wrapper
#  Clicks are handled via st.query_params: ?edit=owner::iter::slot
# ─────────────────────────────────────────────────────────────────────────────
from datetime import date as _date

# ── Check for a click coming in via query param ───────────────────────────
qp = st.query_params
if "edit" in qp and st.session_state.edit is None:
    try:
        parts = qp["edit"].split("::")
        st.session_state.edit = {
            "owner": parts[0], "iter_num": int(parts[1]), "slot": int(parts[2])
        }
        st.query_params.clear()
        st.rerun()
    except Exception:
        st.query_params.clear()

# ── Build month groupings ─────────────────────────────────────────────────
month_seq: list[tuple[str, list[int]]] = []
seen_months: dict = {}
for it in vis_iterations:
    y, m, d = map(int, it["start"].split("-"))
    mk = _date(y, m, 1).strftime("%b %Y")
    if mk not in seen_months:
        seen_months[mk] = len(month_seq)
        month_seq.append((mk, []))
    month_seq[seen_months[mk]][1].append(it["num"])

CELL_W   = 160   # px per task card
LABEL_W  = 130   # px for the row-label column
ITER_W   = 180   # minimum px per iteration column (grows with tasks)


def task_card_inner(owner: str, iter_num: int, slot: int,
                    task: dict, is_team_copy: bool = False) -> str:
    """Return the inner HTML of one task card (no wrapping <td>)."""
    has_content = any(str(v).strip() for k, v in task.items() if k != "iter")
    feature_name = task.get("feature", "").strip()
    bg, border, fg = feature_colours(feature_name)

    # feature filter — render as faded placeholder
    if feature_filter and feature_filter not in feature_name.lower():
        return (f'<div style="width:{CELL_W}px;min-width:{CELL_W}px;margin:2px">'
                f'<div class="task-empty" style="opacity:0.3;line-height:4">filtered</div></div>')

    if is_team_copy:
        if has_content:
            member_task = get_task(data, owner, iter_num, slot)
            member_sp   = str(member_task.get("sp", "")).strip()
            sp_html     = (f'<span class="sp-badge" style="background:{border}">{member_sp}</span>'
                           if member_sp else
                           '<span class="sp-badge" style="background:#aaa;font-size:0.6em">SP?</span>')
            descr = task.get("descr", "").strip()
            lines = []
            if feature_name:
                lines.append(f'<span class="field-label">FEAT</span> {feature_name}')
            if descr:
                lines.append(f'<span class="field-label">DESCR</span> {descr}')
            body     = "<br>".join(lines) or "<em>—</em>"
            edit_url = f"?edit={owner}::{iter_num}::{slot}"
            return (f'<div style="width:{CELL_W}px;min-width:{CELL_W}px;margin:2px">'
                    f'<a href="{edit_url}" target="_self" style="text-decoration:none">'
                    f'<div class="task-card" style="background:{bg};border-color:{border};color:{fg};opacity:0.85">'
                    f'{sp_html}<span class="task-team-badge" style="background:{border}">TEAM</span><br>{body}</div></a></div>')
        return ""   # no team task yet — show nothing in member row

    # Editable slot
    edit_url = f"?edit={owner}::{iter_num}::{slot}"

    if owner == TEAM_OWNER and slot == 0:
        sp_total = get_team_task_sp_sum(data, iter_num)
        sp_html  = (f'<span class="sp-badge" style="background:{border}">{sp_total}</span>'
                    if sp_total > 0 else "")
    else:
        sp      = str(task.get("sp", "")).strip()
        sp_html = f'<span class="sp-badge" style="background:{border}">{sp}</span>' if sp else ""

    if has_content:
        descr = task.get("descr", "").strip()
        ac    = task.get("ac",    "").strip()
        lines = []
        if feature_name:
            lines.append(f'<span class="field-label">FEAT</span> {feature_name}')
        if descr:
            lines.append(f'<span class="field-label">DESCR</span> {descr}')
        if ac:
            lines.append(f'<span class="field-label">AC</span> {ac}')
        body = "<br>".join(lines)
        return (f'<div style="width:{CELL_W}px;min-width:{CELL_W}px;margin:2px">'
                f'<a href="{edit_url}" target="_self" style="text-decoration:none">'
                f'<div class="task-card" style="background:{bg};border-color:{border};color:{fg}">'
                f'{sp_html}{body}</div></a></div>')
    else:
        return (f'<div style="width:{CELL_W}px;min-width:{CELL_W}px;margin:2px">'
                f'<a href="{edit_url}" target="_self" style="text-decoration:none">'
                f'<div class="task-empty">＋</div></a></div>')


def iter_cell_html(owner: str, it: dict, is_team: bool = False) -> str:
    """One <td> for an entire iteration for one owner.
    Contains a flex row of task cards — length is independent per owner."""
    iter_num   = it["num"]
    start_slot = 0 if is_team else 1
    n_slots    = get_slot_count(data, owner, iter_num)

    cards = []
    if not is_team:
        # Always prepend the read-only team-task mirror as the first card
        team_task = get_task(data, TEAM_OWNER, iter_num, 0)
        cards.append(task_card_inner(owner, iter_num, 0, team_task, is_team_copy=True))

    for slot in range(start_slot, n_slots):
        task = get_task(data, owner, iter_num, slot)
        cards.append(task_card_inner(owner, iter_num, slot, task))

    inner = "".join(cards)
    bg = "#F8FBFF" if it["num"] % 2 == 0 else "#FFFFFF"
    return (f'<td style="background:{bg};padding:4px;vertical-align:top;'
            f'border:1px solid #c0cfe0;min-width:{ITER_W}px">'
            f'<div style="display:flex;flex-direction:row;flex-wrap:nowrap;gap:2px">'
            f'{inner}</div></td>')


def row_html(label: str, label_bg: str, label_fg: str,
             owner: str, is_team: bool = False) -> str:
    """One <tr> — label cell + one iter_cell_html per visible iteration."""
    html = (f'<tr><td style="width:{LABEL_W}px;min-width:{LABEL_W}px;background:{label_bg};'
            f'color:{label_fg};font-weight:bold;padding:8px;vertical-align:middle;'
            f'border:1px solid #c0cfe0;word-break:break-word">{label}</td>')
    for it in vis_iterations:
        html += iter_cell_html(owner, it, is_team=is_team)
    html += "</tr>"
    return html


# ── Assemble the full table ───────────────────────────────────────────────
# Each iteration is one column — width is fixed (ITER_W), rows are independent
num_iters = len(vis_iterations)
table_w   = LABEL_W + num_iters * ITER_W   # minimum; will stretch with content

html_parts = [
    '<div style="overflow-x:auto;overflow-y:visible;width:100%;padding-bottom:16px">',
    f'<table style="border-collapse:collapse;min-width:{table_w}px;table-layout:auto">',
]

# Month header
html_parts.append("<tr>")
html_parts.append(f'<th style="width:{LABEL_W}px;min-width:{LABEL_W}px;background:#1F3864;color:white;padding:6px;border:1px solid #3a5a9a">Member</th>')
for mk, itnums in month_seq:
    span = sum(1 for n in itnums if n in {it["num"] for it in vis_iterations})
    html_parts.append(f'<th colspan="{span}" style="background:#2F5496;color:white;text-align:center;font-weight:bold;padding:6px;border:1px solid #3a5a9a">{mk}</th>')
html_parts.append("</tr>")

# Iter header
html_parts.append("<tr>")
html_parts.append(f'<th style="background:#1F3864;color:white;border:1px solid #3a5a9a"></th>')
for it in vis_iterations:
    html_parts.append(f'<th style="min-width:{ITER_W}px;background:#2E75B6;color:white;text-align:center;font-weight:bold;padding:6px;border:1px solid #3a5a9a">{it["label"]}</th>')
html_parts.append("</tr>")

# Date sub-header
html_parts.append("<tr>")
html_parts.append(f'<th style="background:#1F3864;color:white;font-size:0.7em;border:1px solid #3a5a9a">Sprint dates</th>')
for it in vis_iterations:
    html_parts.append(f'<th style="background:#EBF3FB;color:#595959;text-align:center;font-size:0.75em;padding:4px;border:1px solid #c0cfe0">{it["date_range"]}</th>')
html_parts.append("</tr>")

# Team row
html_parts.append(row_html(f'🏷 {data["team_name"]}<br><small>Team Tasks</small>',
                            "#2E75B6", "white", TEAM_OWNER, is_team=True))

# Member rows
member_bgs = ["#BDD7EE", "#D6E4F0"]
for mi, member in enumerate(vis_members):
    bg = member_bgs[mi % 2]
    html_parts.append(row_html(f'👤 {member}', bg, "#1F3864", member))

html_parts.append("</table></div>")

st.markdown("\n".join(html_parts), unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
#  SUMMARY TABLE
# ─────────────────────────────────────────────────────────────────────────────
st.divider()
with st.expander("📊 Task Summary Table", expanded=False):
    rows = []
    all_owners = [TEAM_OWNER] + data["members"]
    for owner in all_owners:
        display = "Team" if owner == TEAM_OWNER else owner
        for it in iterations:
            n_slots = get_slot_count(data, owner, it["num"])
            start_slot = 0 if owner == TEAM_OWNER else 1
            for slot in range(start_slot, n_slots):
                t = get_task(data, owner, it["num"], slot)
                if any(str(v).strip() for k, v in t.items() if k != "iter"):
                    rows.append({
                            "Owner":   display,
                            "Iter":    it["num"],
                            "Slot":    slot + 1,
                            "Feature": t.get("feature", ""),
                            "DESCR":   t.get("descr",   ""),
                            "AC":      t.get("ac",      ""),
                            "SP":      t.get("sp",      ""),
                        })
    if rows:
        import pandas as pd
        df = pd.DataFrame(rows)
        if feature_filter:
            df = df[df["Feature"].str.lower().str.contains(feature_filter, na=False)]
        st.dataframe(df, use_container_width=True, hide_index=True)
        total_sp = sum(int(r["SP"]) for r in rows if str(r["SP"]).isdigit())
        st.caption(f"Total story points across all tasks: **{total_sp} SP**")
    else:
        st.info("No tasks added yet. Click ＋ on the timeline to add one.")

