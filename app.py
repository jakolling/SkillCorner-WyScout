import io
import unicodedata
import pandas as pd
import streamlit as st

st.set_page_config(page_title="🔗 Merge player databases", layout="wide")

st.title("🔗 Merge player databases (Streamlit)")
st.caption("Upload two datasets (Excel or CSV), choose the key column(s) — for example, **Short Name** or **Player** — and merge everything into a single DataFrame. The output is in Excel.")

# -------- Helpers
def read_any(file, sheet=None):
    name = getattr(file, "name", "") if hasattr(file, "name") else str(file)
    if name.lower().endswith(".csv"):
        df = pd.read_csv(file)
        return df, {"type": "csv", "sheets": None, "selected_sheet": None}
    else:
        # Excel: we may have a selected sheet
        xls = pd.ExcelFile(file)
        sheets = xls.sheet_names
        selected = sheet if sheet in sheets else sheets[0]
        df = pd.read_excel(xls, sheet_name=selected)
        return df, {"type": "excel", "sheets": sheets, "selected_sheet": selected}

def normalize_str(s, *, lower=True, strip=True, remove_accents=True):
    if pd.isna(s):
        return s
    s = str(s)
    if remove_accents:
        s = ''.join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn')
    if lower:
        s = s.lower()
    if strip:
        s = s.strip()
    # collapse internal whitespace
    s = ' '.join(s.split())
    return s

def normalize_df_key(df, cols, suffix="__norm"):
    df = df.copy()
    if isinstance(cols, str):
        cols = [cols]
    newcol = "_&_".join(cols) + suffix
    df[newcol] = df[cols].astype(str).agg(" ".join, axis=1).map(lambda x: normalize_str(x))
    return df, newcol

def best_guess_keys(cols1, cols2):
    # Prefer columns that look like short/abbreviated player names
    candidates = ["Short Name", "ShortName", "Player Short Name", "Abbrev", "Abbreviated", "NameShort"]
    # common generic names
    generic = ["Player", "Name"]
    # Find first present in both
    for c in candidates + generic:
        if c in cols1 and c in cols2:
            return [c]
    # Otherwise return any intersection non-empty
    inter = [c for c in cols1 if c in cols2]
    return inter[:1] if inter else []

# -------- Sidebar: inputs
with st.sidebar:
    st.header("⚙️ Input files")
    f1 = st.file_uploader("Dataset 1 (Excel/CSV)", type=["xlsx", "xls", "csv"], key="f1")
    f2 = st.file_uploader("Dataset 2 (Excel/CSV)", type=["xlsx", "xls", "csv"], key="f2")
    use_sample = st.checkbox("Use included sample files", value=not (f1 and f2), help="Uses the two example files provided in this conversation.")
    sheet1 = sheet2 = None

    if use_sample:
        f1 = "Eliteserien 2025 - SC.xlsx"
        f2 = "Eliteserien 2025.xlsx"

    st.markdown("---")
    st.header("🔑 Join keys")
    normalize = st.checkbox("Normalize keys (case, spaces, accents)", value=True)
    merge_how = st.selectbox("Join type", ["inner", "left", "right", "outer"], index=3, help="Select how to combine the rows.")

# -------- Load data
load_error = None
df1 = df2 = meta1 = meta2 = None
try:
    df1, meta1 = read_any(f1, sheet=sheet1)
    df2, meta2 = read_any(f2, sheet=sheet2)
except Exception as e:
    load_error = str(e)

if load_error:
    st.error(f"Error loading files: {load_error}")
    st.stop()

# Optional sheet pickers for Excel
with st.expander("📄 Select sheets (for Excel files)"):
    cols = st.columns(2)
    with cols[0]:
        if meta1["type"] == "excel":
            sel = st.selectbox("Sheet of Dataset 1", meta1["sheets"], index=meta1["sheets"].index(meta1["selected_sheet"]))
            if sel != meta1["selected_sheet"]:
                df1, meta1 = read_any(f1, sheet=sel)
    with cols[1]:
        if meta2["type"] == "excel":
            sel = st.selectbox("Sheet of Dataset 2", meta2["sheets"], index=meta2["sheets"].index(meta2["selected_sheet"]))
            if sel != meta2["selected_sheet"]:
                df2, meta2 = read_any(f2, sheet=sel)

# Guess keys
guess = best_guess_keys(df1.columns.tolist(), df2.columns.tolist())

st.subheader("🧭 Key selection")
key_cols1 = st.multiselect("Column(s) from Dataset 1", options=list(df1.columns), default=guess if guess else [])
key_cols2 = st.multiselect("Column(s) from Dataset 2", options=list(df2.columns), default=guess if guess else [])

if not key_cols1 or not key_cols2 or len(key_cols1) != len(key_cols2):
    st.warning("Select the same number of key columns in both datasets.")
    st.stop()

# Normalize keys if requested
if normalize:
    df1n, key1 = normalize_df_key(df1, key_cols1)
    df2n, key2 = normalize_df_key(df2, key_cols2)
    left_on, right_on = key1, key2
else:
    df1n, df2n = df1, df2
    left_on, right_on = key_cols1 if len(key_cols1) == 1 else key_cols1, key_cols2 if len(key_cols2) == 1 else key_cols2

# Perform merge
with st.spinner("🧬 Merging data..."):
    merged = pd.merge(df1n, df2n, how=merge_how, left_on=left_on, right_on=right_on, suffixes=("_SC", "_SRC2"))

# Rename column Player_SC -> Player for compatibility
if "Player_SC" in merged.columns and "Player" not in merged.columns:
    merged = merged.rename(columns={"Player_SC": "Player"})

st.success(f"✅ Merge completed: {len(merged):,} rows | {len(merged.columns):,} columns")

# Preview and basic filters
st.subheader("👀 Preview")
st.dataframe(merged.head(100), use_container_width=True)

st.subheader("📥 Download (Excel)")
buf = io.BytesIO()
with pd.ExcelWriter(buf, engine="xlsxwriter") as writer:
    merged.to_excel(writer, sheet_name="Merged", index=False)
st.download_button("Download merged Excel", data=buf.getvalue(), file_name="merged_players.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

with st.expander("ℹ️ Tips"):
    st.markdown('''
- Prefer **Short Name** or **Player** when both exist in each dataset.
- Enable **Normalize keys** to ignore case, accents, and spacing differences.
- You can combine multiple columns (e.g., `Short Name` + `Birthdate`) to disambiguate duplicate names.
- Use `outer` to see all records from both sources, then filter as needed.
    ''')
