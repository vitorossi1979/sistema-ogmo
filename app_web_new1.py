import streamlit as st
import pandas as pd
import sqlite3
from datetime import date, datetime
from fpdf import FPDF

# --- 1. CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Sistema OGMO-ES", layout="wide")

# --- 2. SISTEMA DE SENHA (SIMPLIFICADO PARA RODAR LOCAL E WEB) ---
# Se for publicar na web, substitua "ogmo123" por st.secrets["password"]
SENHA_ACESSO = "ogmo123"

def check_password():
    if "password_correct" not in st.session_state:
        st.title("🚢 Portal de Escalação OGMO-ES")
        senha = st.text_input("Digite a senha de acesso:", type="password")
        if st.button("Entrar"):
            if senha == SENHA_ACESSO:
                st.session_state["password_correct"] = True
                st.rerun()
            else:
                st.error("Senha incorreta!")
        return False
    return True

# --- SÓ EXECUTA O SISTEMA SE LOGADO ---
if check_password():

    # --- 3. BANCO DE DADOS ---
    def init_db():
        conn = sqlite3.connect("porto_v2.db", check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS trabalhadores (
            matricula INTEGER PRIMARY KEY, nome TEXT,
            cambio_chefe_basico DATE, cambio_chefe_especial DATE,
            cambio_rodizio DATE, cambio_acordo DATE)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS requisicoes (
            id INTEGER PRIMARY KEY AUTOINCREMENT, navio TEXT, funcao TEXT, vagas INTEGER)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS escolhas (
            id INTEGER PRIMARY KEY AUTOINCREMENT, matricula INTEGER, 
            prioridade INTEGER, requisicao_id INTEGER)''')
        conn.commit()
        return conn

    conn = init_db()

    # --- 4. FUNÇÃO PARA GERAR PDF ---
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
        pdf.cell(80, 10, "Nome", 1, 0, "C", True)
        pdf.cell(50, 10, "Navio", 1, 0, "C", True)
        pdf.cell(35, 10, "Funcao", 1, 1, "C", True)
        
        pdf.set_font("Arial", "", 10)
        for res in dados:
            pdf.cell(25, 10, str(res["Matrícula"]), 1)
            pdf.cell(80, 10, res["Nome"][:35], 1)
            pdf.cell(50, 10, res["Navio"], 1)
            pdf.cell(35, 10, res["Função"], 1, 1)
        
        return pdf.output(dest='S').encode('latin-1', 'replace')

    # --- 5. MENU LATERAL ---
    st.sidebar.title("🚢 Painel de Controle")
    menu = ["🏠 Início", "🚢 Cadastro de Navios", "📝 Lançar Escolhas", "⚙️ Processar Escala", "👤 Cadastrar Trabalhadores", "⚙️ Gerir Trabalhadores"]
    choice = st.sidebar.radio("Navegação:", menu)

    # --- LÓGICA DAS PÁGINAS ---

    if choice == "🏠 Início":
        st.header("Painel Administrativo OGMO-ES")
        st.write(f"Hoje é dia: **{date.today().strftime('%d/%m/%Y')}**")
        st.info("Siga a ordem: 1º Cadastre Navios, 2º Lance Escolhas, 3º Processe a Escala.")

    elif choice == "🚢 Cadastro de Navios":
        st.header("Requisições de Navios")
        with st.form("form_navio"):
            navio = st.text_input("Nome do Navio").upper()
            funcao = st.selectbox("Função", ["RODÍZIO", "CHEFE BÁSICO", "CHEFE ESPECIAL", "ACORDO"])
            vagas = st.number_input("Vagas", min_value=1, step=1)
            if st.form_submit_button("Adicionar"):
                conn.execute("INSERT INTO requisicoes (navio, funcao, vagas) VALUES (?,?,?)", (navio, funcao, vagas))
                conn.commit()
                st.success("Navio cadastrado!")
        
        st.subheader("Vagas do Dia")
        df_req = pd.read_sql("SELECT * FROM requisicoes", conn)
        st.table(df_req)
        if st.button("Limpar Todas as Vagas"):
            conn.execute("DELETE FROM requisicoes"); conn.execute("DELETE FROM escolhas")
            conn.commit(); st.rerun()

    elif choice == "📝 Lançar Escolhas":
        st.header("Preferências dos Trabalhadores")
        reqs = pd.read_sql("SELECT * FROM requisicoes", conn)
        if reqs.empty:
            st.warning("Cadastre os navios primeiro.")
        else:
            with st.form("form_esc"):
                mat = st.number_input("Matrícula", step=1)
                opcoes = [f"{r['id']} | {r['navio']} ({r['funcao']})" for _, r in reqs.iterrows()]
                esc1 = st.selectbox("1ª Opção", ["Nenhuma"] + opcoes)
                esc2 = st.selectbox("2ª Opção", ["Nenhuma"] + opcoes)
                if st.form_submit_button("Gravar Escolhas"):
                    if esc1 != "Nenhuma":
                        conn.execute("INSERT INTO escolhas (matricula, prioridade, requisicao_id) VALUES (?,1,?)", (mat, int(esc1.split(" | ")[0])))
                    if esc2 != "Nenhuma":
                        conn.execute("INSERT INTO escolhas (matricula, prioridade, requisicao_id) VALUES (?,2,?)", (mat, int(esc2.split(" | ")[0])))
                    conn.commit()
                    st.success("Escolhas registradas!")

    elif choice == "⚙️ Processar Escala":
        st.header("Escalação Oficial")
        if st.button("Executar Alocação Inteligente"):
            vagas_raw = conn.execute("SELECT * FROM requisicoes").fetchall()
            vagas_dict = {r[0]: {"navio": r[1], "funcao": r[2], "vagas": r[3]} for r in vagas_raw}
            
            # Ranking: Câmbio Rodízio (Antigo primeiro) e Matrícula (Menor primeiro)
            ranking = pd.read_sql("SELECT * FROM trabalhadores ORDER BY cambio_rodizio ASC, matricula ASC", conn)
            
            resultado = []
            for _, t in ranking.iterrows():
                m = t['matricula']
                escolhas = conn.execute("SELECT requisicao_id FROM escolhas WHERE matricula = ? ORDER BY prioridade ASC", (m,)).fetchall()
                for esc in escolhas:
                    rid = esc[0]
                    if rid in vagas_dict and vagas_dict[rid]['vagas'] > 0:
                        vagas_dict[rid]['vagas'] -= 1
                        resultado.append({"Matrícula": m, "Nome": t['nome'], "Navio": vagas_dict[rid]['navio'], "Função": vagas_dict[rid]['funcao']})
                        break
            
            if resultado:
                st.success("Escala Concluída!")
                st.table(pd.DataFrame(resultado))
                pdf_bytes = exportar_pdf(resultado)
                st.download_button("📥 Baixar Escala em PDF", pdf_bytes, "escala_ogmo.pdf", "application/pdf")
            else:
                st.error("Nenhuma alocação realizada. Verifique se há escolhas e vagas.")

    elif choice == "👤 Cadastrar Trabalhadores":
        st.header("Novo Cadastro")
        with st.form("cad"):
            m = st.number_input("Matrícula", step=1)
            n = st.text_input("Nome").upper()
            d = date.today()
            c1, c2, c3, c4 = st.columns(4)
            cb = c1.date_input("Câmbio Básico", d)
            ce = c2.date_input("Câmbio Especial", d)
            cr = c3.date_input("Câmbio Rodízio", d)
            ca = c4.date_input("Câmbio Acordo", d)
            if st.form_submit_button("Salvar Trabalhador"):
                conn.execute("INSERT OR REPLACE INTO trabalhadores VALUES (?,?,?,?,?,?)", (m, n, cb, ce, cr, ca))
                conn.commit()
                st.success("Cadastrado!")

    elif choice == "⚙️ Gerir Trabalhadores":
        st.header("Gerenciamento")
        df_total = pd.read_sql("SELECT * FROM trabalhadores ORDER BY nome ASC", conn)
        if not df_total.empty:
            lista_trabs = [f"{row['matricula']} - {row['nome']}" for _, row in df_total.iterrows()]
            sel = st.selectbox("Selecione para Editar ou Remover:", ["Nenhum"] + lista_trabs)
            
            if sel != "Nenhum":
                m_sel = int(sel.split(" - ")[0])
                d_at = df_total[df_total['matricula'] == m_sel].iloc[0]
                
                with st.form("edit"):
                    st.subheader(f"Editando: {d_at['nome']}")
                    novo_n = st.text_input("Nome", value=d_at['nome']).upper()
                    def parse_dt(d_str): return datetime.strptime(d_str, '%Y-%m-%d').date() if isinstance(d_str, str) else d_str
                    nc1 = st.date_input("Básico", parse_dt(d_at['cambio_chefe_basico']))
                    nc3 = st.date_input("Rodízio", parse_dt(d_at['cambio_rodizio']))
                    if st.form_submit_button("Atualizar"):
                        conn.execute("UPDATE trabalhadores SET nome=?, cambio_chefe_basico=?, cambio_rodizio=? WHERE matricula=?", (novo_n, nc1, nc3, m_sel))
                        conn.commit(); st.rerun()
                
                if st.button("❌ EXCLUIR DEFINITIVAMENTE", type="primary"):
                    conn.execute("DELETE FROM trabalhadores WHERE matricula=?", (m_sel,))
                    conn.commit(); st.success("Removido!"); st.rerun()
            st.dataframe(df_total)