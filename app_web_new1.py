import streamlit as st
import pandas as pd
import sqlite3
from datetime import date, datetime
from fpdf import FPDF
import io

# --- 1. CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Sistema OGMO-ES v8.0", layout="wide", page_icon="🚢")

# --- 2. SISTEMA DE SENHA E DIRECIONAMENTO INICIAL ---
SENHA_ACESSO = "ogmo123"

def check_password():
    if "password_correct" not in st.session_state:
        st.title("🚢 Portal de Escalação OGMO-ES")
        senha = st.text_input("Senha de Acesso:", type="password")
        if st.button("Entrar no Sistema"):
            if senha == SENHA_ACESSO:
                st.session_state["password_correct"] = True
                # DEFINE A TELA INICIAL PADRÃO PÓS-LOGIN (ADMINISTRADOR -> FECHAMENTO DA ESCALA)
                st.session_state["perfil_padrao"] = "⚙️ Painel do Administrador"
                st.session_state["admin_padrao"] = "⚙️ Fechamento da Escala"
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

    # --- 6. BARRA LATERAL (COM CONTROLE DE TELA INICIAL) ---
    st.sidebar.title("🚢 Painel Integrado")
    
    # Gerencia o índice do perfil padrão pós-login
    lista_perfis = ["👤 Portal do Trabalhador", "⚙️ Painel do Administrador"]
    idx_perfil = lista_perfis.index(st.session_state.get("perfil_padrao", "👤 Portal do Trabalhador"))
    
    perfil = st.sidebar.radio("Selecione seu Perfil:", lista_perfis, index=idx_perfil)
    st.sidebar.divider()

    # Limpa o gatilho inicial se o usuário mudar de perfil manualmente
    if "perfil_padrao" in st.session_state and perfil != st.session_state["perfil_padrao"]:
        st.session_state.pop("perfil_padrao", None)
        st.session_state.pop("admin_padrao", None)

    # ================= ÁREA DO TRABALHADOR =================
    if perfil == "👤 Portal do Trabalhador":
        opc_trab = st.sidebar.radio("Navegação:", ["📝 Lançar Minhas Escolhas", "📊 Quadro de Vagas"])

        if opc_trab == "📝 Lançar Minhas Escolhas":
            st.header("📝 Central de Preferências de Escalação")
            df_trabs = pd.read_sql("SELECT matricula, nome FROM trabalhadores ORDER BY nome ASC", conn)
            reqs = pd.read_sql("SELECT * FROM requisicoes", conn)
            
            if df_trabs.empty or reqs.empty:
                st.warning("⚠️ Sistema indisponível para lançamentos no momento. Aguarde as requisições de hoje.")
            else:
                lista_trabs = [f"{r['matricula']} - {r['nome']}" for _, r in df_trabs.iterrows()]
                trab_sel = st.selectbox("Selecione seu Nome/Matrícula:", lista_trabs)
                mat_atual = int(trab_sel.split(" - ")[0])

                if "lista_escolhas" not in st.session_state: st.session_state.lista_escolhas = []
                
                col_vaga, col_tipo, col_btn = st.columns([3, 2, 1])
                vaga_sel = col_vaga.selectbox("Vaga do Navio", [f"{r['id']} | {r['navio']} ({r['funcao']})" for _, r in reqs.iterrows()])
                tipo_sel = col_tipo.radio("Tipo de Disputa:", ["Com Câmbio", "Sem Câmbio"], horizontal=True)
                
                if col_btn.button("➕ Adicionar Vaga"):
                    st.session_state.lista_escolhas.append({"vaga_id": int(vaga_sel.split(" | ")[0]), "vaga_txt": vaga_sel, "tipo": tipo_sel})

                if st.session_state.lista_escolhas:
                    for i, item in enumerate(st.session_state.lista_escolhas):
                        st.info(f"🎯 **{i+1}ª Opção:** {item['vaga_txt']} — Modo: **{item['tipo']}**")
                    if st.button("🗑️ Limpar Opções"):
                        st.session_state.lista_escolhas = []
                        st.rerun()

                if st.button("💾 CONFIRMAR E GRAVAR PREFERÊNCIAS", type="primary", use_container_width=True):
                    if not st.session_state.lista_escolhas:
                        st.error("Sua lista está vazia.")
                    else:
                        conn.execute("DELETE FROM escolhas WHERE matricula = ?", (mat_atual,))
                        for i, item in enumerate(st.session_state.lista_escolhas):
                            conn.execute("INSERT INTO escolhas (matricula, prioridade, requisicao_id, tipo_disputa) VALUES (?,?,?,?)", 
                                         (mat_atual, i+1, item['vaga_id'], item['tipo']))
                        conn.commit()
                        st.session_state.lista_escolhas = []
                        st.balloons(); st.success("Escolhas gravadas!")

        elif opc_trab == "📊 Quadro de Vagas":
            st.header("📊 Quadro Geral de Vagas")
            df_req = pd.read_sql("SELECT navio as 'Navio', funcao as 'Função', vagas as 'Vagas' FROM requisicoes", conn)
            st.dataframe(df_req, use_container_width=True)

    # ================= ÁREA DO ADMINISTRADOR =================
    elif perfil == "⚙️ Painel do Administrador":
        lista_opcoes_admin = ["🚢 Requisições de Navios", "⚙️ Fechamento da Escala", "👤 Gestão de Trabalhadores"]
        
        # Gerencia o índice da sub-opção padrão (Fechamento da Escala) pós-login
        idx_admin = lista_opcoes_admin.index(st.session_state.get("admin_padrao", "🚢 Requisições de Navios"))
        
        opc_admin = st.sidebar.radio("Funções Administrativas:", lista_opcoes_admin, index=idx_admin)

        # Limpa as variáveis de inicialização forçada assim que o usuário navegar
        if "admin_padrao" in st.session_state and opc_admin != st.session_state["admin_padrao"]:
            st.session_state.pop("perfil_padrao", None)
            st.session_state.pop("admin_padrao", None)

        if opc_admin == "🚢 Requisições de Navios" or opc_admin == "👤 Gestão de Trabalhadores":
            tipo_painel = "Navios" if opc_admin == "🚢 Requisições de Navios" else "Trabalhadores"
            st.header(f"⚙️ Gerenciamento e Carga de {tipo_painel}")

            abas_lista = ["📋 Importação Direta (Texto)", "📂 Carregar Arquivo (Excel/CSV)", "➕ Inclusão Manual"]
            if tipo_painel == "Trabalhadores":
                abas_lista.append("👀 Monitorar Escolhas do Turno")

            abas = st.tabs(abas_lista)
            df_para_salvar = None

            with abas[0]:
                st.write("Cole os dados copiados diretamente das suas colunas do Excel ou bloco de notas:")
                texto_colado = st.text_area("Data", height=150, help="Insira dados em formato estruturado", placeholder="Insira os dados aqui...", key=f"txt_{tipo_painel}")
                c1, c2 = st.columns(2)
                formato_sel = c1.selectbox("Format*", ["Detecção automática", "CSV", "JSON"], key=f"f_{tipo_painel}")
                separador_sel = c2.selectbox("CSV Delimiter", ["Detecção automática", "Ponto e Vírgula", "Vírgula", "Tabulação"], key=f"s_{tipo_painel}")
                if texto_colado:
                    df_para_salvar = processar_texto_puro(texto_colado, separador_sel, formato_sel)

            with abas[1]:
                file_upload = st.file_uploader("Escolha o arquivo para upload:", type=['xlsx', 'csv'], key=f"file_{tipo_painel}")
                if file_upload:
                    df_para_salvar = ler_planilha_arquivo(file_upload)

            with abas[2]:
                if tipo_painel == "Navios":
                    with st.form("f_manual_n"):
                        navio = st.text_input("Nome do Navio").upper()
                        funcao = st.selectbox("Função", ["RODÍZIO", "CHEFE BÁSICO", "CHEFE ESPECIAL", "ACORDO"])
                        vagas = st.number_input("Vagas", min_value=1, step=1)
                        if st.form_submit_button("Adicionar Registro"):
                            conn.execute("INSERT INTO requisicoes (navio, funcao, vagas) VALUES (?,?,?)", (navio, funcao, vagas))
                            conn.commit(); st.success("Adicionado!"); st.rerun()
                else:
                    with st.form("f_manual_t"):
                        m = st.number_input("Matrícula", step=1)
                        n = st.text_input("Nome Completo").upper()
                        col_d1, col_d2, col_d3, col_d4 = st.columns(4)
                        d = date.today()
                        cb = col_d1.date_input("Chefe Básico", d); ce = col_d2.date_input("Chefe Especial", d)
                        cr = col_d3.date_input("Rodízio", d); ca = col_d4.date_input("Acordo", d)
                        if st.form_submit_button("Salvar Trabalhador"):
                            conn.execute("INSERT OR REPLACE INTO trabalhadores VALUES (?,?,?,?,?,?)", (m, n, cb, ce, cr, ca))
                            conn.commit(); st.success("Salvo!"); st.rerun()

            if tipo_painel == "Trabalhadores":
                with abas[3]:
                    st.subheader("📊 Escolhas Lançadas por Nome")
                    query_escolhas = """
                        SELECT t.nome as 'Trabalhador', t.matricula as 'Matrícula', 
                               e.prioridade as 'Preferência (Opção)', r.navio as 'Navio Escolhido', 
                               r.funcao as 'Função da Vaga', e.tipo_disputa as 'Tipo de Disputa'
                        FROM escolhas e
                        JOIN trabalhadores t ON e.matricula = t.matricula
                        JOIN requisicoes r ON e.requisicao_id = r.id
                        ORDER BY t.nome ASC, e.prioridade ASC
                    """
                    df_monitoramento = pd.read_sql(query_escolhas, conn)
                    if df_monitoramento.empty:
                        st.info("💡 Nenhum trabalhador lançou escolhas para este turno ainda.")
                    else:
                        st.dataframe(df_monitoramento, use_container_width=True)

            if df_para_salvar is not None:
                st.write("### Prévia dos Dados Identificados:")
                st.dataframe(df_para_salvar.head(5), use_container_width=True)
