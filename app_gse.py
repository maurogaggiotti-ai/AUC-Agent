import sqlite3
import pandas as pd
import streamlit as st
from datetime import datetime

# ==========================================
# BACKEND: Gestione Database (SQLite)
# ==========================================
class AUCManager:
    def __init__(self, db_path: str = "auc_management.db"):
        # check_same_thread=False è necessario per Streamlit
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self._create_tables()

    def _create_tables(self):
        cursor = self.conn.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS progetti (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            nome_condominio TEXT NOT NULL,
                            indirizzo TEXT,
                            cabina_primaria TEXT NOT NULL,
                            referente_nome TEXT NOT NULL,
                            censimp_code TEXT,
                            stato_pratica TEXT DEFAULT 'Bozza')''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS membri_pod (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            progetto_id INTEGER,
                            nome_proprietario TEXT NOT NULL,
                            codice_fiscale TEXT NOT NULL,
                            pod TEXT NOT NULL,
                            tipo_utenza TEXT CHECK(tipo_utenza IN ('Consumo', 'Produzione', 'Parti Comuni')),
                            liberatoria_firmata BOOLEAN DEFAULT 0,
                            FOREIGN KEY(progetto_id) REFERENCES progetti(id))''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS checklist_gse (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            progetto_id INTEGER,
                            documento TEXT NOT NULL,
                            caricato BOOLEAN DEFAULT 0,
                            verificato BOOLEAN DEFAULT 0,
                            FOREIGN KEY(progetto_id) REFERENCES progetti(id))''')
        self.conn.commit()

    def get_progetti(self):
        return pd.read_sql_query('SELECT * FROM progetti', self.conn)

    def crea_progetto(self, nome, indirizzo, cabina, referente, censimp):
        cursor = self.conn.cursor()
        cursor.execute('''INSERT INTO progetti (nome_condominio, indirizzo, cabina_primaria, referente_nome, censimp_code)
                          VALUES (?, ?, ?, ?, ?)''', (nome, indirizzo, cabina, referente, censimp))
        progetto_id = cursor.lastrowid
        docs_base = ["Verbale Assemblea / Mandato Referente", "Schema Unifilare Impianto", 
                     "Certificato Collaudo / GAUDI CENSIMP", "Documento Identità Referente", 
                     "Autodichiarazione TIAD (da Portale GSE)"]
        for doc in docs_base:
            cursor.execute('INSERT INTO checklist_gse (progetto_id, documento) VALUES (?, ?)', (progetto_id, doc))
        self.conn.commit()

    def get_pod_progetto(self, progetto_id):
        return pd.read_sql_query(f'SELECT * FROM membri_pod WHERE progetto_id = {progetto_id}', self.conn)

    def aggiungi_pod(self, progetto_id, nome, cf, pod, tipo, liberatoria):
        cursor = self.conn.cursor()
        cursor.execute('''INSERT INTO membri_pod (progetto_id, nome_proprietario, codice_fiscale, pod, tipo_utenza, liberatoria_firmata)
                          VALUES (?, ?, ?, ?, ?, ?)''', (progetto_id, nome, cf, pod, tipo, liberatoria))
        self.conn.commit()

    def get_checklist(self, progetto_id):
        return pd.read_sql_query(f'SELECT id, documento, caricato, verificato FROM checklist_gse WHERE progetto_id = {progetto_id}', self.conn)

    def aggiorna_checklist(self, doc_id, caricato, verificato):
        cursor = self.conn.cursor()
        cursor.execute('UPDATE checklist_gse SET caricato = ?, verificato = ? WHERE id = ?', (caricato, verificato, doc_id))
        self.conn.commit()
        
    def aggiorna_stato_pratica(self, progetto_id, nuovo_stato):
        cursor = self.conn.cursor()
        cursor.execute('UPDATE progetti SET stato_pratica = ? WHERE id = ?', (nuovo_stato, progetto_id))
        self.conn.commit()

# ==========================================
# FRONTEND: Interfaccia Utente Streamlit
# ==========================================
st.set_page_config(page_title="Gestione Pratiche AUC GSE", layout="wide")

@st.cache_resource
def init_db():
    return AUCManager()

db = init_db()

st.sidebar.title("🌿 AUC Manager GSE")
st.sidebar.markdown("Strumento di supporto per il Referente (Amministratore).")
menu = st.sidebar.radio("Navigazione", ["Dashboard Progetti", "Nuovo Progetto AUC", "Gestione Dettaglio & POD"])

# --- PAGINA 1: DASHBOARD ---
if menu == "Dashboard Progetti":
    st.title("🏢 Dashboard Progetti Autoconsumo Collettivo")
    progetti_df = db.get_progetti()
    
    if progetti_df.empty:
        st.info("Nessun progetto registrato. Vai su 'Nuovo Progetto AUC' per iniziare.")
    else:
        st.dataframe(progetti_df[['id', 'nome_condominio', 'cabina_primaria', 'referente_nome', 'stato_pratica']], use_container_width=True)

# --- PAGINA 2: NUOVO PROGETTO ---
elif menu == "Nuovo Progetto AUC":
    st.title("📝 Registrazione Nuovo Gruppo AUC")
    st.markdown("Inserisci i dati generali del Condominio e dell'Impianto per inizializzare la pratica.")
    
    with st.form("form_nuovo_progetto"):
        col1, col2 = st.columns(2)
        with col1:
            nome = st.text_input("Nome Condominio (es. Condominio Sole)")
            indirizzo = st.text_input("Indirizzo Completo")
            referente = st.text_input("Nome Referente / Amministratore")
        with col2:
            cabina = st.text_input("Codice Cabina Primaria (es. CP_00123)")
            censimp = st.text_input("Codice Terna CENSIMP (se già disponibile)")
            
        submitted = st.form_submit_button("Crea Progetto")
        if submitted and nome and cabina and referente:
            db.crea_progetto(nome, indirizzo, cabina, referente, censimp)
            st.success(f"Progetto '{nome}' creato con successo! Ora puoi gestire i POD e i documenti.")

# --- PAGINA 3: GESTIONE DETTAGLIO & POD ---
elif menu == "Gestione Dettaglio & POD":
    st.title("⚙️ Gestione Pratica GSE")
    
    progetti_df = db.get_progetti()
    if progetti_df.empty:
        st.warning("Nessun progetto disponibile.")
    else:
        # Selezione Progetto
        opzioni_progetti = {row['id']: f"{row['nome_condominio']} (ID: {row['id']})" for _, row in progetti_df.iterrows()}
        progetto_selezionato = st.selectbox("Seleziona il Progetto da gestire:", options=list(opzioni_progetti.keys()), format_func=lambda x: opzioni_progetti[x])
        
        dettagli_progetto = progetti_df[progetti_df['id'] == progetto_selezionato].iloc[0]
        
        # Gestione Stato Pratica
        st.subheader("Stato della Pratica sul Portale")
        stati_disponibili = ['Bozza', 'Raccolta Dati', 'Istanza in Compilazione GSE', 'Istruttoria GSE (In Attesa)', 'Accettata/Attiva', 'Integrazione Richiesta']
        indice_stato_attuale = stati_disponibili.index(dettagli_progetto['stato_pratica']) if dettagli_progetto['stato_pratica'] in stati_disponibili else 0
        
        nuovo_stato = st.selectbox("Aggiorna lo stato:", stati_disponibili, index=indice_stato_attuale)
        if nuovo_stato != dettagli_progetto['stato_pratica']:
            db.aggiorna_stato_pratica(progetto_selezionato, nuovo_stato)
            st.success("Stato pratica aggiornato!")
            st.rerun()

        st.divider()

        # --- TAB: MEMBRI E POD ---
        tab1, tab2 = st.tabs(["👥 Membri e POD", "📄 Checklist Documenti GSE"])
        
        with tab1:
            st.markdown("### Elenco Utenze (POD) Partecipanti")
            pod_df = db.get_pod_progetto(progetto_selezionato)
            
            if not pod_df.empty:
                st.dataframe(pod_df[['nome_proprietario', 'codice_fiscale', 'pod', 'tipo_utenza', 'liberatoria_firmata']], use_container_width=True)
                
                # Funzione di esportazione CSV (Formato utile per GSE)
                csv = pod_df[['nome_proprietario', 'codice_fiscale', 'pod', 'tipo_utenza']].to_csv(index=False).encode('utf-8')
                st.download_button(
                    label="⬇️ Esporta Lista POD in CSV (Per GSE)",
                    data=csv,
                    file_name=f"Lista_POD_AUC_{dettagli_progetto['nome_condominio']}.csv",
                    mime="text/csv",
                )
            else:
                st.info("Nessun POD inserito per questo progetto.")
                
            st.markdown("#### Aggiungi nuovo POD")
            with st.form("form_aggiungi_pod", clear_on_submit=True):
                c1, c2 = st.columns(2)
                with c1:
                    nome_prop = st.text_input("Nome Condòmino / Proprietario")
                    cf = st.text_input("Codice Fiscale / P.IVA")
                with c2:
                    pod_code = st.text_input("Codice POD (Inizia con IT...)")
                    tipo = st.selectbox("Tipo di Utenza", ["Consumo", "Produzione", "Parti Comuni"])
                lib = st.checkbox("Liberatoria trattamento dati firmata dal condòmino")
                
                sub_pod = st.form_submit_button("Aggiungi Utenza")
                if sub_pod and nome_prop and cf and pod_code:
                    db.aggiungi_pod(progetto_selezionato, nome_prop, cf, pod_code, tipo, lib)
                    st.success("POD aggiunto correttamente!")
                    st.rerun()

        # --- TAB: DOCUMENTAZIONE ---
        with tab2:
            st.markdown("### Checklist Documentazione Obbligatoria")
            st.caption("Usa questa checklist per assicurarti di avere tutti i file prima di accedere al portale GSE.")
            
            check_df = db.get_checklist(progetto_selezionato)
            
            for index, row in check_df.iterrows():
                col_a, col_b, col_c = st.columns([3, 1, 1])
                with col_a:
                    st.write(f"📄 **{row['documento']}**")
                with col_b:
                    is_caricato = st.checkbox("Caricato su PC", value=bool(row['caricato']), key=f"caricato_{row['id']}")
                with col_c:
                    is_verif = st.checkbox("Verificato per GSE", value=bool(row['verificato']), key=f"verificato_{row['id']}")
                
                # Se i valori cambiano, aggiorna il DB
                if is_caricato != bool(row['caricato']) or is_verif != bool(row['verificato']):
                    db.aggiorna_checklist(row['id'], is_caricato, is_verif)
                    st.rerun()
