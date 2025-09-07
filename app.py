
import io
import unicodedata
import pandas as pd
import streamlit as st

st.set_page_config(page_title="🔗 Unir bases de dados de jogadores", layout="wide")

st.title("🔗 Unir bases de dados de jogadores (Streamlit)")
st.caption("Carregue duas bases (Excel ou CSV), escolha a(s) coluna(s) de chave — por exemplo, **Short Name** ou **Player** — e una tudo em um único DataFrame. A saída é em Excel.")

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
    candidates = ["Short Name", "ShortName", "Player Short Name", "Nome Curto", "Abbrev", "Abbreviated", "NameShort"]
    # common generic names
    generic = ["Player", "Jogador", "Name", "Nome"]
    # Find first present in both
    for c in candidates + generic:
        if c in cols1 and c in cols2:
            return [c]
    # Otherwise return any intersection non-empty
    inter = [c for c in cols1 if c in cols2]
    return inter[:1] if inter else []

# -------- Sidebar: inputs
with st.sidebar:
    st.header("⚙️ Arquivos de entrada")
    f1 = st.file_uploader("Base 1 (Excel/CSV)", type=["xlsx", "xls", "csv"], key="f1")
    f2 = st.file_uploader("Base 2 (Excel/CSV)", type=["xlsx", "xls", "csv"], key="f2")
    use_sample = st.checkbox("Usar arquivos de exemplo incluídos", value=not (f1 and f2), help="Usa os dois arquivos enviados na conversa como exemplo.")
    sheet1 = sheet2 = None

    if use_sample:
        f1 = "Eliteserien 2025 - SC.xlsx"
        f2 = "Eliteserien 2025.xlsx"

    st.markdown("---")
    st.header("🔑 Chaves de união")
    normalize = st.checkbox("Normalizar chaves (case, espaços, acentos)", value=True)
    merge_how = st.selectbox("Tipo de junção", ["inner", "left", "right", "outer"], index=3, help="Selecione como quer combinar as linhas.")

# -------- Load data
load_error = None
df1 = df2 = meta1 = meta2 = None
try:
    df1, meta1 = read_any(f1, sheet=sheet1)
    df2, meta2 = read_any(f2, sheet=sheet2)
except Exception as e:
    load_error = str(e)

if load_error:
    st.error(f"Erro ao carregar os arquivos: {load_error}")
    st.stop()

# Optional sheet pickers for Excel
with st.expander("📄 Selecionar planilhas (para arquivos Excel)"):
    cols = st.columns(2)
    with cols[0]:
        if meta1["type"] == "excel":
            sel = st.selectbox("Planilha da Base 1", meta1["sheets"], index=meta1["sheets"].index(meta1["selected_sheet"]))
            if sel != meta1["selected_sheet"]:
                df1, meta1 = read_any(f1, sheet=sel)
    with cols[1]:
        if meta2["type"] == "excel":
            sel = st.selectbox("Planilha da Base 2", meta2["sheets"], index=meta2["sheets"].index(meta2["selected_sheet"]))
            if sel != meta2["selected_sheet"]:
                df2, meta2 = read_any(f2, sheet=sel)

# Guess keys
guess = best_guess_keys(df1.columns.tolist(), df2.columns.tolist())

st.subheader("🧭 Seleção das chaves")
key_cols1 = st.multiselect("Coluna(s) da Base 1", options=list(df1.columns), default=guess if guess else [])
key_cols2 = st.multiselect("Coluna(s) da Base 2", options=list(df2.columns), default=guess if guess else [])

if not key_cols1 or not key_cols2 or len(key_cols1) != len(key_cols2):
    st.warning("Selecione a(s) mesma(s) quantidade(s) de colunas de chave em ambas as bases.")
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
with st.spinner("🧬 Unindo dados..."):
    merged = pd.merge(df1n, df2n, how=merge_how, left_on=left_on, right_on=right_on, suffixes=("_SC", "_SRC2"))

# Renomear coluna Player_SC -> Player para compatibilidade com seus softwares
if "Player_SC" in merged.columns and "Player" not in merged.columns:
    merged = merged.rename(columns={"Player_SC": "Player"})

st.success(f"✅ União concluída: {len(merged):,} linhas | {len(merged.columns):,} colunas")

# Preview and basic filters
st.subheader("👀 Pré-visualização")
st.dataframe(merged.head(100), use_container_width=True)

st.subheader("📥 Download (Excel)")
buf = io.BytesIO()
with pd.ExcelWriter(buf, engine="xlsxwriter") as writer:
    merged.to_excel(writer, sheet_name="Merged", index=False)
st.download_button("Baixar Excel unificado", data=buf.getvalue(), file_name="merged_players.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

with st.expander("ℹ️ Dicas"):
    st.markdown('''
- Prefira **Short Name** ou **Player** quando ambas existirem em cada base.
- Ative **Normalizar chaves** para ignorar diferenças de maiúsculas/minúsculas, acentos e espaços.
- Pode combinar múltiplas colunas (ex.: `Short Name` + `Birthdate`) para desambiguar homônimos.
- Use `outer` para ver todos os registros de ambas as fontes, e depois filtre conforme necessário.
    ''')
