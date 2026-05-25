import streamlit as st
import pandas as pd
import sqlite3
from datetime import date, datetime
from fpdf import FPDF
import io

# --- 1. CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(
    page_title="Sistema OGMO-ES v8.2", 
    layout="wide", 
    page_icon="🚢"
)

# --- 2. SISTEMA DE SENHA ---
SENHA_ACESSO = "ogmo123"

def check_password():
    if "password_correct" not in st.session_state:
        st.title("🚢 Portal de Escalação OGMO-ES")
        senha = st.text_input("Senha de Acesso:", type="password")
        if st.button("Entrar no Sistema"):
            if senha == SENHA_ACESSO:
                st.session_state["password_correct"] = True
                st.rerun()
            else:
                st.error("Senha incorreta!")
        return False
    return True

if check_password():

    # --- 3. BANCO DE DADOS ---
    def init_db():
        conn = sqlite3.connect("porto_v7_oficial.db", check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS trabalhadores (
            matricula INTEGER PRIMARY KEY, nome TEXT,
            cambio_chefe_basico DATE, cambio_chefe_especial DATE,
            cambio_rodizio DATE, cambio_acordo DATE)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS requisicoes (
            id INTEGER PRIMARY KEY AUTOINCREMENT, navio TEXT, funcao TEXT, vagas INTEGER)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS escolhas (
            id INTEGER PRIMARY KEY AUTOINCREMENT, matricula INTEGER, 
            prioridade INTEGER, requisicao_id INTEGER, tipo_disputa TEXT)''')
        conn.commit()
        return conn

    conn = init_db()

    # --- 4. ENGINE DE TRATAMENTO DE TEXTO/PLANILHA ---
    def processar_texto_puro(texto, separador, formato):
        if not texto.strip():
            return None
        try:
            data_io = io.StringIO(texto.strip())
            sep = ',' if separador == "Vírgula" else ';' if separador == "Ponto e Vírgula" else '\t'
            
            if formato == "CSV":
                return pd.read_csv(data_io, sep=sep, encoding='utf-8')
            elif formato == "JSON":
                return pd.read_json(data_io)
            else:
                if '\t' in texto:
                    return pd.read_csv(data_io, sep='\t')
                return pd.read_csv(data_io, sep=None, engine='python')
        except Exception as e:
            st.error(f"Erro ao processar o texto digitado: {e}")
            return None

    def ler_planilha_arquivo(file):
        if file.name.endswith('xlsx'):
            return pd.read_excel(file)
        else:
            for enc in ['iso-8859-1', 'utf-8', 'cp1252']:
                for sep in [';', ',', '\t']:
                    try:
                        file.seek(0)
                        df = pd.read_csv(file, sep=sep, encoding=enc)
                        if len(df.columns) > 1: return df
                    except: continue
            file.seek(0)
            return pd.read_csv(file, sep=None, engine='python', encoding='iso-8859-1')

    # --- 5. FUNÇÃO PARA GERAR PDF ---
    def exportar_pdf(dados):
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", "B", 16)
        pdf.cell(190, 10, "OGMO-ES - RELATORIO DE ESCALACAO", ln=True, align="C")
        pdf.set_font("Arial", "", 10)
        pdf.cell(190, 10, f"Data: {date.today().strftime('%d/%m/%Y')}", ln=True, align="C")
        pdf.ln(10)
        pdf.set_fill_color(200, 200, 200)
        pdf.set_font("Arial", "B", 10)
        pdf.cell(25, 10, "Matricula", 1, 0, "C", True)
        pdf.cell(75, 10, "Nome", 1, 0, "C", True)
        pdf.cell(45, 10, "Navio", 1, 0, "C", True)
        pdf.cell(25, 10, "Funcao", 1, 0, "C", True)
        pdf.cell(20, 10, "Tipo", 1, 1, "C", True)
        pdf.set_font("Arial", "", 9)
        for res in dados:
            pdf.cell(25, 10, str(res["Matrícula"]), 1)
            pdf.cell(75, 10, str(res["Nome"])[:30], 1)
            pdf.cell(45, 10, str(res["Navio"]), 1)
            pdf.cell(25, 10, str(res["Função"]), 1)
            pdf.cell(20, 10, str(res["Critério"]), 1, 1)
        return pdf.output(dest='S').encode('latin-1', 'replace')

    # --- 6. NAVEGAÇÃO DIRETA NA TELA PRINCIPAL ---
    st.title("🚢 Painel Integrado de Escalação")
    
    # Seleção do Perfil direto no topo da tela principal (ótimo para Mobile)
    perfil = st.radio(
        "Selecione seu Perfil:", 
        ["⚙️ Painel do Administrador", "👤 Portal do Trabalhador"], 
        horizontal=True
    )
    st.divider()

    # ================= ÁREA DO ADMINISTRADOR (ABRE PRIMEIRO) =================
    if perfil == "⚙️ Painel do Administrador":
        
        # Menu de funções administrativas transformado em abas grandes na tela principal
        aba_admin_1, aba_admin_2, aba_admin_3 = st.tabs([
            "⚙️ Fechamento da Escala", 
            "🚢 Requisições de Navios", 
            "👤 Gestão de Trabalhadores"
        ])

        # --- ABA 1: FECHAMENTO DA ESCALA (TELA INICIAL PADRÃO) ---
        with aba_admin_1:
            st.header("⚙️ Fechamento e Processamento da Escala Oficial")
            
            if "escala_gerada" not in st.session_state:
                st.session_state.escala_gerada = None

            if st.button("🚀 Executar Alocação de Turno", type="primary", use_container_width=True):
                vagas = pd.read_sql("SELECT * FROM requisicoes", conn)
                trabs = pd.read_sql("SELECT * FROM trabalhadores", conn)
                escolhas = pd.read_sql("SELECT * FROM escolhas ORDER BY prioridade ASC", conn)
                
                resultado = []; ja_escalados = set()
                vagas_restantes = {r['id']: r['vagas'] for _, r in vagas.iterrows()}

                # Rodada 1: Categoria "Com Câmbio"
                for _, vaga in vagas.iterrows():
                    f = vaga['funcao']
                    col = {"RODÍZIO": "cambio_rodizio", "CHEFE BÁSICO": "cambio_chefe_basico", "CHEFE ESPECIAL": "cambio_chefe_especial", "ACORDO": "cambio_acordo"} .get(f, "cambio_rodizio")
                    int_c = escolhas[(escolhas['requisicao_id'] == vaga['id']) & (escolhas['tipo_disputa'] == "Com Câmbio")]
                    int_c = int_c.merge(trabs, on='matricula').sort_values(by=[col, 'matricula'])
                    for _, p in int_c.iterrows():
                        if vagas_restantes[vaga['id']] > 0 and p['matricula'] not in ja_escalados:
                            vagas_restantes[vaga['id']] -= 1; ja_escalados.add(p['matricula'])
                            resultado.append({"Matrícula": p['matricula'], "Nome": p['nome'], "Navio": vaga['navio'], "Função": vaga['funcao'], "Critério": "Com Câmbio"})

                # Rodada 2: Categoria "Sem Câmbio"
                for _, vaga in vagas.iterrows():
                    if vagas_restantes[vaga['id']] > 0:
                        int_sc = escolhas[(escolhas['requisicao_id'] == vaga['id']) & (escolhas['tipo_disputa'] == "Sem Câmbio")]
                        int_sc = int_sc.merge(trabs, on='matricula').sort_values(by='matricula', ascending=True)
                        for _, p in int_sc.iterrows():
                            if vagas_restantes[vaga['id']] > 0 and p['matricula'] not in ja_escalados:
                                vagas_restantes[vaga['id']] -= 1; ja_escalados.add(p['matricula'])
                                resultado.append({"Matrícula": p['matricula'], "Nome": p['nome'], "Navio": vaga['navio'], "Função": vaga['funcao'], "Critério": "Sem Câmbio"})

                if resultado:
                    st.session_state.escala_gerada = resultado
                    st.success("Escala Oficial Concluída!")
                else:
                    st.session_state.escala_gerada = None
                    st.error("Nenhuma alocação realizada com as escolhas atuais.")

            if st.session_state.escala_gerada:
                st.write("---")
                st.subheader("📋 Resultado Homologado do Turno")
                st.dataframe(pd.DataFrame(st.session_state.escala_gerada), use_container_width=True)
                
                pdf_bytes = exportar_pdf(st.session_state.escala_gerada)
                
                c_pdf, c_limpar = st.columns([1, 1])
                c_pdf.download_button("📥 Baixar Escala Homologada em PDF", pdf_bytes, f"escala_{date.today().strftime('%Y-%m-%d')}.pdf", "application/pdf", use_container_width=True)
                
                if c_limpar.button("🚨 Limpar Escolhas Deste Turno", type="secondary", use_container_width=True):
                    conn.execute("DELETE FROM escolhas")
                    conn.commit()
                    st.session_state.escala_gerada = None
                    st.toast("Tabela de escolhas limpa com sucesso!", icon="🗑️")
                    st.success("As escolhas foram deletadas. O sistema está pronto para o próximo turno!")
                    st.rerun()

        # --- ABA 2: REQUISIÇÕES DE NAVIOS ---
        with aba_admin_2:
            st.header("⚙️ Gerenciamento e Carga de Navios")
            abas_carga = st.tabs(["📋 Importação Direta (Texto)", "📂 Carregar Arquivo (Excel/CSV)", "➕ Inclusão Manual"])
            df_para_salvar = None

            with abas_carga[0]:
                texto_colado = st.text_area("Cole os dados aqui:", height=150, key="txt_Navios")
                c1, c2 = st.columns(2)
                formato_sel = c1.selectbox("Formato", ["Detecção automática", "CSV", "JSON"], key="f_Navios")
                separador_sel = c2.selectbox("Delimitador CSV", ["Detecção automática", "Ponto e Vírgula", "Vírgula", "Tabulação"], key="s_Navios")
                if texto_colado: df_para_salvar = processar_texto_puro(texto_colado, separador_sel, formato_sel)

            with abas_carga[1]:
                file_upload = st.file_uploader("Escolha o arquivo:", type=['xlsx', 'csv'], key="file_Navios")
                if file_upload: df_para_salvar = ler_planilha_arquivo(file_upload)

            with abas_carga[2]:
                with st.form("f_manual_n"):
                    navio = st.text_input("Nome do Navio").upper()
                    funcao = st.selectbox("Função", ["RODÍZIO", "CHEFE BÁSICO", "CHEFE ESPECIAL", "ACORDO"])
                    vagas = st.number_input("Vagas", min_value=1, step=1)
                    if st.form_submit_button("Adicionar Registro"):
                        conn.execute("INSERT INTO requisicoes (navio, funcao, vagas) VALUES (?,?,?)", (navio, funcao, vagas))
                        conn.commit(); st.success("Adicionado!"); st.rerun()

            if df_para_salvar is not None:
                st.dataframe(df_para_salvar.head(5), use_container_width=True)
                if st.button("Confirmar Envio e Salvar Navios", type="primary"):
                    try:
                        df_para_salvar.columns = df_para_salvar.columns.str.strip().str.lower()
                        for _, r in df_para_salvar.iterrows():
                            conn.execute("INSERT INTO requisicoes (navio, funcao, vagas) VALUES (?,?,?)", (str(r['navio']).upper(), str(r['funcao']).upper(), int(r['vagas'])))
                        conn.commit(); st.success("Navios importados!"); st.rerun()
                    except Exception as e: st.error(f"Erro: {e}")

            st.subheader("Registros Atuais de Vagas/Navios")
            df_req = pd.read_sql("SELECT id, navio, funcao, vagas FROM requisicoes", conn)
            st.dataframe(df_req, use_container_width=True)
            if st.button("🚨 Limpar Todas as Vagas e Escolhas", key="btn_limpar_vagas"):
                conn.execute("DELETE FROM requisicoes"); conn.execute("DELETE FROM escolhas"); conn.commit(); st.rerun()

        # --- ABA 3: GESTÃO DE TRABALHADORES ---
        with aba_admin_3:
            st.header("⚙️ Gerenciamento e Carga de Trabalhadores")
            abas_trab = st.tabs(["📋 Importação Direta (Texto)", "📂 Carregar Arquivo (Excel/CSV)", "➕ Inclusão Manual", "👀 Monitorar Escolhas"])
            df_para_salvar_t = None

            with abas_trab[0]:
                texto_colado_t = st.text_area("Cole os dados aqui:", height=150, key="txt_Trabs")
                c1, c2 = st.columns(2)
                formato_sel_t = c1.selectbox("Formato", ["Detecção automática", "CSV", "JSON"], key="f_Trabs")
                separador_sel_t = c2.selectbox("Delimitador CSV", ["Detecção automática", "Ponto e Vírgula", "Vírgula", "Tabulação"], key="s_Trabs")
                if texto_colado_t: df_para_salvar_t = processar_texto_puro(texto_colado_t, separador_sel_t, formato_sel_t)

            with abas_trab[1]:
                file_upload_t = st.file_uploader("Escolha o arquivo:", type=['xlsx', 'csv'], key="file_Trabs")
                if file_upload_t: df_para
