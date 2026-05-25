import streamlit as st
import pandas as pd
import sqlite3
from datetime import date, datetime
from fpdf import FPDF
import io

# --- 1. CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Sistema OGMO-ES v7.8", layout="wide", page_icon="🚢")

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

    # --- 6. BARRA LATERAL ---
    st.sidebar.title("🚢 Painel Integrado")
    perfil = st.sidebar.radio("Selecione seu Perfil:", ["👤 Portal do Trabalhador", "⚙️ Painel do Administrador"])
    st.sidebar.divider()

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
        opc_admin = st.sidebar.radio("Funções Administrativas:", ["🚢 Requisições de Navios", "⚙️ Fechamento da Escala", "👤 Gestão de Trabalhadores"])

        if opc_admin == "🚢 Requisições de Navios" or opc_admin == "👤 Gestão de Trabalhadores":
            tipo_painel = "Navios" if opc_admin == "🚢 Requisições de Navios" else "Trabalhadores"
            st.header(f"⚙️ Gerenciamento e Carga de {tipo_painel}")

            # Menu de Abas expandido com monitoramento caso seja Trabalhadores
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

            # Monitoramento em Tempo Real das escolhas individuais
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

            # --- TRATAMENTO ROBUSTO E SALVAMENTO DE DADOS ---
            if df_para_salvar is not None:
                st.write("### Prévia dos Dados Identificados:")
                st.dataframe(df_para_salvar.head(5), use_container_width=True)
                
                col_btn_cancela, col_btn_envia = st.columns([10, 1])
                if col_btn_envia.button("Enviar", type="primary", use_container_width=True):
                    try:
                        df_para_salvar.columns = df_para_salvar.columns.str.strip().str.lower()
                        mapeamento_colunas = {
                            'função': 'funcao', 'matrícula': 'matricula',
                            'câmbio chefe básico': 'cambio_chefe_basico', 'câmbio chefe especial': 'cambio_chefe_especial',
                            'câmbio rodízio': 'cambio_rodizio', 'câmbio acordo': 'cambio_acordo'
                        }
                        df_para_salvar.rename(columns=mapeamento_colunas, inplace=True)

                        if tipo_painel == "Navios":
                            for _, r in df_para_salvar.iterrows():
                                conn.execute("INSERT INTO requisicoes (navio, funcao, vagas) VALUES (?,?,?)", 
                                             (str(r['navio']).upper(), str(r['funcao']).upper(), int(r['vagas'])))
                        else:
                            for _, r in df_para_salvar.iterrows():
                                conn.execute("INSERT OR REPLACE INTO trabalhadores VALUES (?,?,?,?,?,?)", 
                                             (int(r['matricula']), str(r['nome']).upper(), str(r['cambio_chefe_basico']), 
                                              str(r['cambio_chefe_especial']), str(r['cambio_rodizio']), str(r['cambio_acordo'])))
                        conn.commit()
                        st.success(f"Dados de {tipo_painel} importados com sucesso!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erro de estrutura: Verifique as colunas. Erro: {e}")

            # Seção Inferior: Opções de Campos
            st.write("---")
            st.subheader("📋 Opções de Campos Aceitos")
            if tipo_painel == "Navios":
                dados_campos = [
                    {"CAMPO": "navio", "OBRIGATÓRIO": "✔", "ACESSADOR": "—", "DESCRIÇÃO": "Nome do navio (Texto)"},
                    {"CAMPO": "funcao", "OBRIGATÓRIO": "✔", "ACESSADOR": "—", "DESCRIÇÃO": "Função (RODÍZIO, CHEFE BÁSICO, CHEFE ESPECIAL, ACORDO)"},
                    {"CAMPO": "vagas", "OBRIGATÓRIO": "✔", "ACESSADOR": "—", "DESCRIÇÃO": "Quantidade de vagas disponíveis (Número)"}
                ]
                st.table(pd.DataFrame(dados_campos))
            else:
                dados_campos = [
                    {"CAMPO": "matricula", "OBRIGATÓRIO": "✔", "ACESSADOR": "—", "DESCRIÇÃO": "Número de matrícula único (Número)"},
                    {"CAMPO": "nome", "OBRIGATÓRIO": "✔", "ACESSADOR": "id", "DESCRIÇÃO": "Nome completo do trabalhador (Texto)"},
                    {"CAMPO": "cambio_chefe_basico", "OBRIGATÓRIO": "✔", "ACESSADOR": "—", "DESCRIÇÃO": "Data do câmbio (AAAA-MM-DD)"},
                    {"CAMPO": "cambio_chefe_especial", "OBRIGATÓRIO": "✔", "ACESSADOR": "—", "DESCRIÇÃO": "Data do câmbio (AAAA-MM-DD)"},
                    {"CAMPO": "cambio_rodizio", "OBRIGATÓRIO": "✔", "ACESSADOR": "—", "DESCRIÇÃO": "Data do câmbio (AAAA-MM-DD)"},
                    {"CAMPO": "cambio_acordo", "OBRIGATÓRIO": "✔", "ACESSADOR": "—", "DESCRIÇÃO": "Data do câmbio (AAAA-MM-DD)"}
                ]
                st.table(pd.DataFrame(dados_campos))

            # Exibição do Banco Atual com Edição Inline e Exclusão
            st.subheader(f"Registros Atuais de {tipo_painel}")
            if tipo_painel == "Navios":
                df_req = pd.read_sql("SELECT id, navio, funcao, vagas FROM requisicoes", conn)
                st.dataframe(df_req, use_container_width=True)
                if st.button("🚨 Limpar Todas as Vagas e Escolhas do Turno"):
                    conn.execute("DELETE FROM requisicoes"); conn.execute("DELETE FROM escolhas"); conn.commit(); st.rerun()
            else:
                df_total = pd.read_sql("SELECT * FROM trabalhadores ORDER BY nome ASC", conn)
                
                # Cabeçalho da Lista
                st.markdown("**Layout: Nome | Matrícula | Câmbios (Básico / Especial / Rodízio / Acordo) | Ações**")
                
                for index, row in df_total.iterrows():
                    # Formatação visual inline das informações atuais
                    texto_cambios = f"📅 Básico: {row['cambio_chefe_basico']} | Esp: {row['cambio_chefe_especial']} | Rod: {row['cambio_rodizio']} | Aco: {row['cambio_acordo']}"
                    
                    c_info, c_edit, c_del = st.columns([6, 1, 1])
                    c_info.write(f"👤 **{row['nome']}** (Matrícula: {row['matricula']})  \n*{texto_cambios}*")
                    
                    # Estado dinâmico para abrir formulário de edição do trabalhador
                    key_editar = f"edit_{row['matricula']}"
                    if c_edit.button("✏️ Editar", key=key_editar):
                        st.session_state[f"active_edit_{row['matricula']}"] = True
                        
                    if c_del.button("🗑️ Excluir", key=f"del_{row['matricula']}"):
                        conn.execute("DELETE FROM trabalhadores WHERE matricula = ?", (row['matricula'],))
                        conn.execute("DELETE FROM escolhas WHERE matricula = ?", (row['matricula'],))
                        conn.commit()
                        st.success(f"Trabalhador {row['nome']} removido!")
                        st.rerun()
                    
                    # Painel Expansível de Edição se o botão for acionado
                    if st.session_state.get(f"active_edit_{row['matricula']}", False):
                        with st.form(f"form_edicao_{row['matricula']}"):
                            st.write(f"⚙️ Alterar dados de: {row['nome']}")
                            novo_nome = st.text_input("Nome Completo", value=row['nome']).upper()
                            
                            # Parse simples de string para objeto date
                            def para_data(s): return datetime.strptime(s, "%Y-%m-%d").date() if s else date.today()
                            
                            ed1, ed2, ed3, ed4 = st.columns(4)
                            ncb = ed1.date_input("Chefe Básico", para_data(row['cambio_chefe_basico']))
                            nce = ed2.date_input("Chefe Especial", para_data(row['cambio_chefe_especial']))
                            ncr = ed3.date_input("Rodízio", para_data(row['cambio_rodizio']))
                            nca = ed4.date_input("Acordo", para_data(row['cambio_acordo']))
                            
                            ce_salvar, ce_cancela = st.columns([1, 1])
                            if ce_salvar.form_submit_button("💾 Salvar Alterações"):
                                conn.execute("""
                                    UPDATE trabalhadores 
                                    SET nome=?, cambio_chefe_basico=?, cambio_chefe_especial=?, cambio_rodizio=?, cambio_acordo=?
                                    WHERE matricula=?
                                """, (novo_nome, str(ncb), str(nce), str(ncr), str(nca), row['matricula']))
                                conn.commit()
                                st.session_state[f"active_edit_{row['matricula']}"] = False
                                st.success("Atualizado!")
                                st.rerun()
                            if ce_cancela.form_submit_button("Cancelar"):
                                st.session_state[f"active_edit_{row['matricula']}"] = False
                                st.rerun()
                    st.divider()

        # 2. FECHAMENTO DA ESCALA (COM LOGICA DE DESEMPATE CORRIGIDA)
        elif opc_admin == "⚙️ Fechamento da Escala":
            st.header("⚙️ Fechamento e Processamento da Escala Oficial")
            if st.button("🚀 Executar Alocação de Turno", type="primary", use_container_width=True):
                vagas = pd.read_sql("SELECT * FROM requisicoes", conn)
                trabs = pd.read_sql("SELECT * FROM trabalhadores", conn)
                escolhas = pd.read_sql("SELECT * FROM escolhas ORDER BY prioridade ASC", conn)
                
                resultado = []; ja_escalados = set()
                vagas_restantes = {r['id']: r['vagas'] for _, r in vagas.iterrows()}

                # Rodada 1: Categoria "Com Câmbio" (Critério: Data do câmbio mais antiga, desempata em matrícula)
                for _, vaga in vagas.iterrows():
                    f = vaga['funcao']
                    col = {"RODÍZIO": "cambio_rodizio", "CHEFE BÁSICO": "cambio_chefe_basico", "CHEFE ESPECIAL": "cambio_chefe_especial", "ACORDO": "cambio_acordo"}.get(f, "cambio_rodizio")
                    int_c = escolhas[(escolhas['requisicao_id'] == vaga['id']) & (escolhas['tipo_disputa'] == "Com Câmbio")]
                    int_c = int_c.merge(trabs, on='matricula').sort_values(by=[col, 'matricula'])
                    for _, p in int_c.iterrows():
                        if vagas_restantes[vaga['id']] > 0 and p['matricula'] not in ja_escalados:
                            vagas_restantes[vaga['id']] -= 1; ja_escalados.add(p['matricula'])
                            resultado.append({"Matrícula": p['matricula'], "Nome": p['nome'], "Navio": vaga['navio'], "Função": vaga['funcao'], "Critério": "Com Câmbio"})

                # Rodada 2: Categoria "Sem Câmbio" (CORRIGIDO: Critério absoluto de MENOR MATRÍCULA)
                for _, vaga in vagas.iterrows():
                    if vagas_restantes[vaga['id']] > 0:
                        int_sc = escolhas[(escolhas['requisicao_id'] == vaga['id']) & (escolhas['tipo_disputa'] == "Sem Câmbio")]
                        # Ordena estritamente de forma crescente pela matrícula do trabalhador
                        int_sc = int_sc.merge(trabs, on='matricula').sort_values(by='matricula', ascending=True)
                        for _, p in int_sc.iterrows():
                            if vagas_restantes[vaga['id']] > 0 and p['matricula'] not in ja_escalados:
                                vagas_restantes[vaga['id']] -= 1; ja_escalados.add(p['matricula'])
                                resultado.append({"Matrícula": p['matricula'], "Nome": p['nome'], "Navio": vaga['navio'], "Função": vaga['funcao'], "Critério": "Sem Câmbio"})

                if resultado:
                    st.success("Escala Oficial Concluída!")
                    st.dataframe(pd.DataFrame(resultado), use_container_width=True)
                    pdf_bytes = exportar_pdf(resultado)
                    st.download_button("📥 Baixar Escala Homologada em PDF", pdf_bytes, f"escala_{date.today().strftime('%Y-%m-%d')}.pdf", "application/pdf")
                else:
                    st.error("Nenhuma alocação realizada.")
