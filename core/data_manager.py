import os
import json
import re
import streamlit as st
import pandas as pd
import datetime
from collections import Counter, defaultdict
import random
import firebase_admin
from firebase_admin import credentials, firestore

# --- Constantes ---
# Caminhos para os arquivos .txt agora dentro da pasta 'data/'
CARTOES_FILE_BASE = 'data/cartoes_validacao.txt'
GPT_FILE_BASE = 'data/Dados_Manual_output_GPT.txt'
CLOZE_FILE_BASE = 'data/Dados_Manual_Cloze_text.txt'
SENTENCE_WORDS_FILE = 'data/palavras_unicas_por_tipo.txt'

# Nomes base para as coleções no Firestore
DB_COLLECTION_NAME = 'vocab'
WRITING_LOG_COLLECTION_NAME = 'writing_log'
HISTORY_COLLECTION_NAME = 'history'
SENTENCE_LOG_COLLECTION_NAME = 'sentence_log'

# Definir as colunas requeridas para o DataFrame do vocabulário
REQUIRED_VOCAB_COLS = {
    "palavra": object, "ativa": bool, "fonte": object,
    "data_adicao": 'datetime64[ns]', "escrita_completa": bool,
    "progresso": object, "mastery_count": int
}

# --- Inicialização do Firebase ---
@st.cache_resource
def init_firebase():
    print("DEBUG: Tentando inicializar Firebase...")
    if firebase_admin._apps:
        print("DEBUG: Firebase já inicializado.")
        return firestore.client()

    try:
        # Tenta carregar as credenciais do Streamlit secrets (para deploy)
        creds_dict = st.secrets["firebase_credentials"]
        print(f"DEBUG: Conteúdo de st.secrets['firebase_credentials'] (tipo: {type(creds_dict)}): {creds_dict}")
        creds = credentials.from_service_account_info(creds_dict)
        firebase_admin.initialize_app(creds)
        print("DEBUG: Firebase inicializado com Streamlit secrets.")
    except KeyError:
        print("DEBUG: Streamlit secrets não encontrados. Tentando fallback local...")
        # Fallback para desenvolvimento local (assumindo arquivo na raiz do projeto)
        try:
            # Caminho mais robusto para o arquivo de credenciais
            # Sobe um nível do diretório 'core' para a raiz do projeto
            cred_path = os.path.join(os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir)), "canada-2c772-firebase-adminsdk-fbsvc-94a6e8f185.json")
            print(f"DEBUG: Caminho de credenciais local sendo verificado: {cred_path}")
            if os.path.exists(cred_path):
                # Carrega o JSON do arquivo e passa o dicionário para from_service_account_info
                with open(cred_path, 'r') as f:
                    file_creds = json.load(f)
                print(f"DEBUG: Conteúdo do arquivo de credenciais local (tipo: {type(file_creds)}): {file_creds}")
                creds = credentials.Certificate.from_service_account_info(file_creds)
                firebase_admin.initialize_app(creds)
                print("DEBUG: Firebase inicializado com arquivo local.")
            else:
                st.error("Arquivo de credenciais do Firebase não encontrado para desenvolvimento local.")
                print(f"ERRO: Arquivo de credenciais não encontrado em {cred_path}")
                return None
        except Exception as e_local:
            st.error(f"Falha ao inicializar o Firebase localmente: {e_local}")
            print(f"ERRO: Falha ao inicializar Firebase localmente: {e_local}")
            return None
    except Exception as e:
        st.error(f"Erro inesperado ao inicializar Firebase: {e}")
        print(f"ERRO: Erro inesperado ao inicializar Firebase: {e}")
        return None
    
    return firestore.client()

db = init_firebase()

# --- Classes de Erro Personalizadas ---
class ParsingError(Exception):
    """Exceção para erros durante o parsing de ficheiros de dados."""
    pass

# --- Funções de Leitura de Arquivos Base (do repositório) ---
# Estas funções leem os arquivos .txt que estarão no GitHub, agora na pasta 'data/'
@st.cache_data
def carregar_flashcards_from_file(language):
    filepath = CARTOES_FILE_BASE
    print(f"DEBUG: Carregando flashcards de: {filepath}")
    if not os.path.exists(filepath):
        print(f"ERRO: Arquivo ANKI não encontrado: {os.path.abspath(filepath)}")
        return [], [f"Arquivo ANKI não encontrado. Caminho verificado: '{os.path.abspath(filepath)}'"]
    with open(filepath, 'r', encoding='utf-8') as f:
        texto = f.read()
    blocos = texto.strip().split('\n\n')
    flashcards, errors = [], []
    target_lang_str = "English" if language == 'en' else "Francais"
    for i, bloco in enumerate(blocos):
        try:
            linhas = [l.strip() for l in bloco.split('\n') if l.strip()]
            if not linhas: continue
            header_match = re.search(r"(.+?)\s+\((.+?)\s*\|\s*(.+?)\s*\|\s*(.+?)\):", linhas[0])
            if not header_match:
                errors.append(f"Cabeçalho mal formatado no bloco ANKI #{i+1}: {linhas[0]}")
                continue
            card_lang = header_match.group(4).strip()
            if card_lang.lower() != target_lang_str.lower(): continue
            card = {"front": header_match.group(1).strip(), "type": header_match.group(2).strip(), "level": header_match.group(3).strip()}
            for linha in linhas[1:]:
                if ": " in linha:
                    key, value = linha.split(':', 1)
                    key = key.strip().lstrip('-').strip()
                    key_map = {'frase en': 'example', 'tradução': 'back', 'tradução frase': 'translation_sentence', 'outra frase en': 'other_example', 'significado': 'significado', 'sinônimo': 'cloze_answer', 'tags': 'tags'}
                    card_key = key_map.get(key.lower())
                    if card_key: card[card_key] = value.strip() if card_key != 'tags' else [t.strip() for t in value.split(',')]
            if not card.get("front") or not card.get("back"):
                errors.append(f"Cartão para '{card.get('front', 'N/A')}' não tem 'front' ou 'back'.")
                continue
            flashcards.append(card)
        except Exception as e:
            errors.append(f"Erro ao processar bloco ANKI #{i+1}: {e}")
    print(f"DEBUG: Carregados {len(flashcards)} flashcards para {language}.")
    return flashcards, errors

@st.cache_data
def carregar_gpt_from_file(language):
    gpt_file = GPT_FILE_BASE
    print(f"DEBUG: Carregando exercícios GPT de: {gpt_file}")
    if not os.path.exists(gpt_file):
        print(f"ERRO: Arquivo GPT não encontrado: {os.path.abspath(gpt_file)}")
        return [], [f"Arquivo de exercícios GPT não encontrado: '{os.path.abspath(gpt_file)}'"]
    with open(gpt_file, encoding='utf-8') as f:
        linhas = [l.strip() for l in f if l.strip()]
    exercicios, errors = [], []
    for i, linha in enumerate(linhas):
        try:
            if ';' not in linha: continue
            partes = [p.strip() for p in linha.split(';')]
            if not partes or len(partes) != 7:
                raise ParsingError(f"Linha de exercício padrão não tem 7 colunas, mas {len(partes)}.")
            idioma_linha, tipo, frase, opcoes_str, correta, principal, cefr_level = partes
            if idioma_linha != language: continue
            if not tipo.startswith(('1-', '2-', '3-', '4-', '5-', '6-')): continue
            if not all([tipo, frase, opcoes_str, correta, principal, cefr_level]):
                raise ParsingError("Uma das colunas obrigatórias está vazia.")
            opcoes_lista = [o.strip() for o in opcoes_str.split('|')]
            if not opcoes_lista or not all(opcoes_lista):
                raise ParsingError("Opções inválidas.")
            exercicios.append({"tipo": tipo, "frase": frase, "opcoes": opcoes_lista, "correta": correta, "principal": principal, "cefr_level": cefr_level})
        except Exception as e:
            errors.append(f"Erro ao processar linha GPT #{i+1} ('{linha[:40]}...'): {e}")
    print(f"DEBUG: Carregados {len(exercicios)} exercícios GPT para {language}.")
    return exercicios, errors

@st.cache_data
def carregar_cloze_from_file(language):
    cloze_file = CLOZE_FILE_BASE
    print(f"DEBUG: Carregando exercícios Cloze de: {cloze_file}")
    if not os.path.exists(cloze_file):
        print(f"ERRO: Arquivo Cloze não encontrado: {os.path.abspath(cloze_file)}")
        return [], [f"Arquivo Cloze não encontrado: '{os.path.abspath(cloze_file)}'"]
    with open(cloze_file, encoding='utf-8') as f:
        linhas = [l.strip() for l in f if l.strip()]
    exercicios, errors = [], []
    for i, linha in enumerate(linhas):
        try:
            if ';' not in linha: continue
            partes = [p.strip() for p in linha.split(';')]
            if not partes or len(partes) != 7:
                raise ParsingError(f"Linha de Cloze-Text não tem 7 colunas, mas {len(partes)}.")
            idioma_linha, tipo, frase, opcoes_str, corretas_str, cefr_level, titulo = partes
            if idioma_linha != language or tipo != '7-Cloze-Text': continue
            opcoes_lista = [o.strip() for o in opcoes_str.split('|')]
            corretas_lista = [c.strip() for c in corretas_str.split('|')]
            exercicios.append({"tipo": tipo, "frase": frase, "opcoes": opcoes_lista, "correta": corretas_lista, "principal": corretas_lista, "cefr_level": cefr_level, "titulo": titulo})
        except Exception as e:
            errors.append(f"Erro ao processar linha Cloze #{i+1} ('{linha[:40]}...'): {e}")
    print(f"DEBUG: Carregados {len(exercicios)} exercícios Cloze para {language}.")
    return exercicios, errors

# --- Funções de Gerenciamento de Dados com Firestore ---

def get_collection_name(base_name, language):
    """Gera o nome da coleção no Firestore."""
    return f"{base_name}_{language}"

@st.cache_data
def load_and_cache_data(language):
    """Carrega e armazena em cache os dados dos arquivos base."""
    flashcards, anki_errors = carregar_flashcards_from_file(language)
    gpt_exercicios, gpt_errors = carregar_gpt_from_file(language)
    cloze_exercicios, cloze_errors = carregar_cloze_from_file(language)
    
    todos_exercicios = gpt_exercicios + cloze_exercicios
    errors = anki_errors + gpt_errors + cloze_errors
    
    st.session_state[f'parsing_errors_{language}'] = errors
    print(f"DEBUG: load_and_cache_data para {language} concluído. Flashcards: {len(flashcards)}, Exercícios GPT/Cloze: {len(todos_exercicios)}")
    return flashcards, todos_exercicios

def sync_database(language):
    """
    Sincroniza o banco de dados do Firestore com as palavras dos arquivos base.
    Retorna um DataFrame do Pandas com os dados atualizados.
    """
    print(f"DEBUG: Iniciando sync_database para {language}...")
    if not db:
        print("ERRO: Cliente Firestore não disponível. Retornando DataFrame vazio com colunas padrão.")
        return pd.DataFrame(columns=REQUIRED_VOCAB_COLS.keys())

    collection_name = get_collection_name(DB_COLLECTION_NAME, language)
    print(f"DEBUG: Acessando coleção: {collection_name}")
    
    docs = db.collection(collection_name).stream()
    db_data = [doc.to_dict() for doc in docs]
    print(f"DEBUG: Dados brutos do Firestore: {len(db_data)} documentos.")

    # Inicializa o DataFrame com as colunas corretas, mesmo que db_data esteja vazio
    db_df = pd.DataFrame(db_data)
    
    # Garante que todas as colunas necessárias existam e tenham o tipo correto
    for col, dtype in REQUIRED_VOCAB_COLS.items():
        if col not in db_df.columns:
            if dtype == bool:
                db_df[col] = False
            elif dtype == int:
                db_df[col] = 0
            else:
                db_df[col] = None # Use None para object/datetime para evitar NaN inicial
        
        # Converte tipos de dados, tratando NaT para datetime
        if dtype == 'datetime64[ns]':
            db_df[col] = pd.to_datetime(db_df[col], errors='coerce')
        elif dtype == bool:
            db_df[col] = db_df[col].astype(bool)
        elif dtype == int:
            db_df[col] = db_df[col].fillna(0).astype(int) # Preenche NaN com 0 antes de converter para int

    # Reordena as colunas para garantir consistência
    db_df = db_df[list(REQUIRED_VOCAB_COLS.keys())]

    print(f"DEBUG: DataFrame inicializado/recarregado. Colunas: {db_df.columns.tolist()}, Linhas: {len(db_df)}")

    # Lógica de sincronização (similar à original)
    flashcards, todos_exercicios = load_and_cache_data(language)
    flashcards_map = {card['front']: card for card in flashcards}
    
    gpt_exercicios_map = defaultdict(list)
    palavras_gpt = set()
    for ex in todos_exercicios:
        # Certifica-se de que 'principal' é uma lista para iteração consistente
        principais = ex.get('principal')
        if not isinstance(principais, list):
            principais = [principais] if principais is not None else []

        for p in principais:
            if p: # Garante que a palavra não é vazia
                gpt_exercicios_map[p].append(ex)
                palavras_gpt.add(p)

    todas_palavras = set(flashcards_map.keys()).union(palavras_gpt)
    palavras_db = set(db_df['palavra'].dropna().unique()) if 'palavra' in db_df.columns and not db_df.empty else set()
    novas_palavras = todas_palavras - palavras_db
    print(f"DEBUG: Novas palavras a serem adicionadas: {len(novas_palavras)}")

    if novas_palavras:
        now = datetime.datetime.now(datetime.timezone.utc)
        batch = db.batch()
        for p in novas_palavras:
            fonte = "ANKI" if p in flashcards_map else "GPT"
            exercicios_palavra = get_available_exercise_types_for_word(p, flashcards_map, gpt_exercicios_map)
            progresso = {identificador: "nao_testado" for identificador in exercicios_palavra.keys()}
            
            new_word_data = {
                "palavra": p, "ativa": True, "fonte": fonte, 
                "data_adicao": now, "escrita_completa": False, 
                "progresso": progresso, "mastery_count": 0
            }
            
            doc_ref = db.collection(collection_name).document(p)
            batch.set(doc_ref, new_word_data)
        
        batch.commit()
        print("DEBUG: Novas palavras adicionadas ao Firestore. Recarregando DataFrame...")
        # Recarrega os dados após adicionar novas palavras
        docs = db.collection(collection_name).stream()
        db_data = [doc.to_dict() for doc in docs]
        db_df = pd.DataFrame(db_data, columns=REQUIRED_VOCAB_COLS.keys()) # Garante colunas no recarregamento

        # Garante que os tipos de dados estejam corretos para colunas booleanas e inteiras após recarregamento
        for col, dtype in REQUIRED_VOCAB_COLS.items():
            if col in db_df.columns:
                if dtype == 'datetime64[ns]':
                    db_df[col] = pd.to_datetime(db_df[col], errors='coerce')
                elif dtype == bool:
                    db_df[col] = db_df[col].astype(bool)
                elif dtype == int:
                    db_df[col] = db_df[col].fillna(0).astype(int)

    print(f"DEBUG: sync_database finalizado. DataFrame tem {len(db_df)} linhas e colunas: {db_df.columns.tolist()}")
    return db_df

def save_vocab_db(df, language):
    """Salva o DataFrame de vocabulário no Firestore."""
    print(f"DEBUG: Iniciando save_vocab_db para {language}...")
    if not db or df.empty: 
        print("DEBUG: Cliente Firestore não disponível ou DataFrame vazio. Nada para salvar.")
        return

    collection_name = get_collection_name(DB_COLLECTION_NAME, language)
    batch = db.batch()
    for _, row in df.iterrows():
        doc_ref = db.collection(collection_name).document(row['palavra'])
        data_to_save = row.to_dict()
        # Converte Timestamps para formato compatível com Firestore
        for key, value in data_to_save.items():
            if isinstance(value, pd.Timestamp):
                data_to_save[key] = value.to_pydatetime()
            elif pd.isna(value):
                data_to_save[key] = None
        batch.set(doc_ref, data_to_save)
    batch.commit()
    print(f"DEBUG: save_vocab_db finalizado para {language}.")

def get_history(language):
    """Carrega o histórico de um documento único no Firestore."""
    print(f"DEBUG: Iniciando get_history para {language}...")
    if not db: 
        print("DEBUG: Cliente Firestore não disponível. Retornando histórico vazio.")
        return {"quiz": [], "gpt_quiz": [], "mixed_quiz": []}
    
    doc_ref = db.collection(get_collection_name(HISTORY_COLLECTION_NAME, language)).document('user_history')
    doc = doc_ref.get()
    history_data = doc.to_dict() if doc.exists else {"quiz": [], "gpt_quiz": [], "mixed_quiz": []}
    print(f"DEBUG: get_history finalizado. Dados: {len(history_data.get('quiz',[]))} quizzes, {len(history_data.get('gpt_quiz',[]))} gpt_quizzes, {len(history_data.get('mixed_quiz',[]))} mixed_quizzes.")
    return history_data

def save_history(historico, language):
    """Salva o histórico em um documento único no Firestore."""
    print(f"DEBUG: Iniciando save_history para {language}...")
    if not db: 
        print("DEBUG: Cliente Firestore não disponível. Nada para salvar histórico.")
        return
    doc_ref = db.collection(get_collection_name(HISTORY_COLLECTION_NAME, language)).document('user_history')
    doc_ref.set(historico)
    print(f"DEBUG: save_history finalizado para {language}.")

def clear_history(language):
    """Limpa o histórico de desempenho no Firestore."""
    print(f"DEBUG: Iniciando clear_history para {language}...")
    if not db: 
        print("DEBUG: Cliente Firestore não disponível. Não é possível limpar histórico.")
        return
    db.collection(get_collection_name(HISTORY_COLLECTION_NAME, language)).document('user_history').delete()
    st.success("Histórico de desempenho online foi limpo com sucesso!")
    print(f"DEBUG: clear_history finalizado para {language}.")

def get_writing_log(language):
    """Carrega o log de escrita do Firestore."""
    print(f"DEBUG: Iniciando get_writing_log para {language}...")
    if not db: 
        print("DEBUG: Cliente Firestore não disponível. Retornando log de escrita vazio.")
        return []
    collection_name = get_collection_name(WRITING_LOG_COLLECTION_NAME, language)
    docs = db.collection(collection_name).order_by("timestamp", direction=firestore.Query.DESCENDING).stream()
    log_data = [doc.to_dict() for doc in docs]
    print(f"DEBUG: get_writing_log finalizado. {len(log_data)} entradas.")
    return log_data

def add_writing_entry(entry, language):
    """Adiciona uma nova entrada ao log de escrita no Firestore."""
    print(f"DEBUG: Iniciando add_writing_entry para {language}...")
    if not db: 
        print("DEBUG: Cliente Firestore não disponível. Não é possível adicionar entrada de escrita.")
        return
    collection_name = get_collection_name(WRITING_LOG_COLLECTION_NAME, language)
    entry['timestamp'] = firestore.SERVER_TIMESTAMP # Adiciona um timestamp do servidor
    doc_ref = db.collection(collection_name).document()
    entry['doc_id'] = doc_ref.id # Salva o ID do documento para facilitar a exclusão
    doc_ref.set(entry)
    
    # Atualiza o status 'escrita_completa' no vocabulário
    vocab_collection = get_collection_name(DB_COLLECTION_NAME, language)
    db.collection(vocab_collection).document(entry['palavra']).update({"escrita_completa": True})
    print(f"DEBUG: add_writing_entry finalizado para {language}.")

def delete_writing_entries(entries_to_delete, language):
    """Deleta entradas do log de escrita no Firestore."""
    print(f"DEBUG: Iniciando delete_writing_entries para {language}...")
    if not db or not entries_to_delete: 
        print("DEBUG: Cliente Firestore não disponível ou nenhuma entrada para deletar.")
        return
    
    collection_name = get_collection_name(WRITING_LOG_COLLECTION_NAME, language)
    batch = db.batch()
    for entry in entries_to_delete:
        if 'doc_id' in entry: # Garante que a entrada tem um ID de documento
            doc_ref = db.collection(collection_name).document(entry['doc_id'])
            batch.delete(doc_ref)
    batch.commit()
    print(f"DEBUG: delete_writing_entries finalizado para {language}.")

def load_sentence_log(language):
    """Carrega o log de frases escritas pelo utilizador do Firestore."""
    print(f"DEBUG: Iniciando load_sentence_log para {language}...")
    if not db: 
        print("DEBUG: Cliente Firestore não disponível. Retornando log de frases vazio.")
        return []
    collection_name = get_collection_name(SENTENCE_LOG_COLLECTION_NAME, language)
    docs = db.collection(collection_name).order_by("timestamp", direction=firestore.Query.DESCENDING).stream()
    log_data = [doc.to_dict() for doc in docs]
    print(f"DEBUG: load_sentence_log finalizado. {len(log_data)} entradas.")
    return log_data

def save_sentence_log(log_data, language):
    """Salva o log de frases escritas pelo utilizador no Firestore."""
    print(f"DEBUG: Iniciando save_sentence_log para {language}...")
    if not db: 
        print("DEBUG: Cliente Firestore não disponível. Não é possível salvar log de frases.")
        return
    collection_name = get_collection_name(SENTENCE_LOG_COLLECTION_NAME, language)
    batch = db.batch()
    for entry in log_data:
        if 'palavra_chave' in entry: # Usar 'palavra_chave' como ID do documento para evitar duplicatas
            doc_ref = db.collection(collection_name).document(entry['palavra_chave'])
            entry['timestamp'] = firestore.SERVER_TIMESTAMP
            batch.set(doc_ref, entry)
    batch.commit()
    print(f"DEBUG: save_sentence_log finalizado para {language}.")

def delete_sentence_log_entry(word_key, language):
    """Apaga uma entrada específica do log de frases no Firestore."""
    print(f"DEBUG: Iniciando delete_sentence_log_entry para {language} com word_key: {word_key}...")
    if not db: 
        print("DEBUG: Cliente Firestore não disponível. Não é possível deletar entrada de frase.")
        return
    db.collection(get_collection_name(SENTENCE_LOG_COLLECTION_NAME, language)).document(word_key).delete()
    print(f"DEBUG: delete_sentence_log_entry finalizado para {language}.")

# --- Funções Utilitárias e de Lógica ---

def get_session_db(language):
    """Obtém o DataFrame do banco de dados de vocabulário da sessão ou sincroniza com o Firestore."""
    session_key = f"db_df_{language}"
    if session_key not in st.session_state:
        st.session_state[session_key] = sync_database(language)
    return st.session_state[session_key]

def update_progress_from_quiz(quiz_results, language):
    """Atualiza o progresso das palavras no DataFrame e no Firestore após um quiz."""
    print(f"DEBUG: Iniciando update_progress_from_quiz para {language} com {len(quiz_results)} resultados.")
    db_df = get_session_db(language)
    if db_df.empty: 
        print("DEBUG: DataFrame de vocabulário vazio, não é possível atualizar o progresso.")
        return
    
    deactivated_words = []
    
    for palavra, resultado, identificador_exercicio, tipo_exercicio in quiz_results:
        idx_list = db_df.index[db_df['palavra'] == palavra].tolist()
        if not idx_list: 
            print(f"DEBUG: Palavra '{palavra}' não encontrada no DataFrame. Pulando atualização.")
            continue
        idx = idx_list[0]
        
        progresso = db_df.at[idx, 'progresso']
        if not isinstance(progresso, dict): progresso = {}
        
        if identificador_exercicio in progresso:
            progresso[identificador_exercicio] = resultado
        else:
            print(f"DEBUG: Identificador de exercício '{identificador_exercicio}' não encontrado para a palavra '{palavra}'. Adicionando.")
            progresso[identificador_exercicio] = resultado
            
        db_df.at[idx, 'progresso'] = progresso
        
        # Verifica se todos os exercícios para a palavra foram acertados
        if all(status == 'acerto' for status in progresso.values()):
            if db_df.at[idx, 'ativa']:
                db_df.at[idx, 'ativa'] = False
                db_df.at[idx, 'mastery_count'] = int(db_df.at[idx, 'mastery_count'] + 1)
                deactivated_words.append(palavra)
                print(f"DEBUG: Palavra '{palavra}' desativada e mastery_count incrementado.")
                
    save_vocab_db(db_df, language)
    st.session_state[f"db_df_{language}"] = db_df # Atualiza o DataFrame na sessão
    if deactivated_words: 
        st.session_state['deactivated_words_notification'] = deactivated_words
        print(f"DEBUG: Palavras desativadas para notificação: {deactivated_words}")
    print(f"DEBUG: update_progress_from_quiz finalizado para {language}.")

def delete_cloze_exercises(exercises_to_delete, language):
    """
    Esta função originalmente modificava um arquivo local.
    No ambiente online (Streamlit Cloud), o sistema de arquivos é efêmero.
    Portanto, esta função não terá efeito persistente e deve ser revisada
    se a intenção for gerenciar exercícios Cloze dinamicamente no Firestore.
    Por enquanto, apenas exibe um aviso.
    """
    st.warning("A exclusão de exercícios Cloze base não é suportada na versão online. As alterações não serão persistentes.")
    print(f"AVISO: Tentativa de deletar exercícios Cloze para {language}. Esta operação não é persistente no Streamlit Cloud.")
    # Se você quiser que a exclusão seja persistente, precisaria de uma coleção no Firestore
    # para armazenar os exercícios Cloze e modificá-la aqui.
    pass

def reset_quiz_state(prefix):
    """Limpa o estado da sessão relacionado a um quiz específico."""
    print(f"DEBUG: Resetando estado do quiz com prefixo: {prefix}")
    keys_to_del = [k for k in st.session_state.keys() if k.startswith(prefix)]
    for k in keys_to_del:
        del st.session_state[k]
    print(f"DEBUG: Estado do quiz com prefixo '{prefix}' limpo.")

def load_sentence_data(language):
    """Carrega as palavras e metadados do ficheiro de frases."""
    filepath = SENTENCE_WORDS_FILE
    print(f"DEBUG: Carregando dados de frases de: {filepath}")
    if not os.path.exists(filepath):
        print(f"ERRO: Arquivo de frases não encontrado: {os.path.abspath(filepath)}")
        return {}
    
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    target_note_type = "BASE English" if language == 'en' else "BASE French"
    words_data = {}
    
    blocos = content.strip().split('\n\n')
    for bloco in blocos:
        linhas = bloco.strip().split('\n')
        if not linhas:
            continue

        palavra = ""
        dados = {}
        
        for linha in linhas:
            if linha.lower().startswith("palavra:"):
                palavra = linha.split(":", 1)[1].strip()
            elif ":" in linha:
                chave, valor = linha.split(":", 1)
                dados[chave.strip().lstrip('-').strip()] = valor.strip()

        if palavra and dados.get("Tipo de Nota") == target_note_type:
            classe = dados.get('Classe', 'N/A')
            unique_key = f"{palavra} ({classe})"
            dados['palavra_base'] = palavra
            words_data[unique_key] = dados
            
    print(f"DEBUG: Carregados {len(words_data)} dados de frases para {language}.")
    return words_data

# --- GERADORES DE QUESTÕES (CENTRALIZADOS) ---
# Estas funções não interagem diretamente com o armazenamento, então permanecem como estão.
def gerar_mcq_significado(cartao, baralho):
    correta = cartao.get("back", "")
    if not correta: return None, None, None, None, None, None
    outros = [c["back"] for c in baralho if c["front"] != cartao["front"] and c.get("back")]
    distractors = random.sample(outros, min(3, len(outros)))
    opcoes = list(set([correta] + distractors))
    random.shuffle(opcoes)
    pergunta = f'What does "<span class="keyword-highlight">{cartao["front"]}</span>" mean?'
    return 'MCQ Significado', pergunta, opcoes, opcoes.index(correta), cartao.get('level'), f"significado::{correta}"

def gerar_mcq_traducao_ingles(cartao, baralho):
    correta = cartao["front"]
    outros = [c["front"] for c in baralho if c["front"] != cartao["front"]]
    distractors = random.sample(outros, min(3, len(outros)))
    opcoes = list(set([correta] + distractors))
    random.shuffle(opcoes)
    pergunta = f'Qual palavra em inglês corresponde a: "<span class="keyword-highlight">{cartao["back"]}</span>"?'
    return 'MCQ Tradução Inglês', pergunta, opcoes, opcoes.index(correta), cartao.get('level'), f"traducao::{cartao.get('back')}"

def gerar_mcq_sinonimo(cartao, baralho):
    correta = cartao.get("cloze_answer", "")
    if not correta: return None, None, None, None, None, None
    outros = [c.get("cloze_answer") for c in baralho if c["front"] != cartao["front"] and c.get("cloze_answer")]
    distractors = random.sample(outros, min(3, len(outros)))
    opcoes = list(set([correta] + distractors))
    random.shuffle(opcoes)
    pergunta = f'Selecione o sinônimo de "<span class="keyword-highlight">{cartao["front"]}</span>":'
    return 'MCQ Sinônimo', pergunta, opcoes, opcoes.index(correta), cartao.get('level'), f"sinonimo::{correta}"

def gerar_fill_gap(cartao, baralho):
    palavra = cartao['front']
    frase = cartao.get('example', '')
    if not frase: return None, None, None, None, None, None
    frase_gap = re.sub(rf'{re.escape(palavra)}', '_____', frase, count=1, flags=re.IGNORECASE)
    if frase_gap == frase: return None, None, None, None, None, None
    correta = palavra
    outros = [c["front"] for c in baralho if c["front"].lower() != palavra.lower()]
    distractors = random.sample(outros, min(3, len(outros)))
    opcoes = [correta] + distractors
    random.shuffle(opcoes)
    return 'Fill', frase_gap, opcoes, opcoes.index(correta), cartao.get('level'), f"fill::{frase}"

def gerar_reading_comprehension(cartao, baralho):
    palavra = cartao["front"]
    frase_exemplo = cartao.get("example", "")
    if not frase_exemplo: return None, None, None, None, None, None
    frase_destacada = re.sub(rf'{re.escape(palavra)}', f'<span class="keyword-highlight">{palavra}</span>', frase_exemplo, count=1, flags=re.IGNORECASE)
    pergunta = (f'Na frase: "{frase_destacada}"<br><br>'
                f'O que provavelmente significa a palavra "<span class="keyword-highlight">{palavra}</span>" nesse contexto?')
    resposta_correta = cartao["back"]
    opcoes = [resposta_correta]
    outros_significados = [c["back"] for c in baralho if c["front"] != cartao["front"] and c.get("back")]
    opcoes += random.sample(outros_significados, min(3, len(outros_significados)))
    random.shuffle(opcoes)
    return 'Reading', pergunta, opcoes, opcoes.index(resposta_correta), cartao.get('level'), f"reading::{frase_exemplo}"

TIPOS_EXERCICIO_ANKI = {
    "MCQ Significado": gerar_mcq_significado, "MCQ Tradução Inglês": gerar_mcq_traducao_ingles,
    "MCQ Sinônimo": gerar_mcq_sinonimo, "Fill": gerar_fill_gap, "Reading": gerar_reading_comprehension
}

def get_exercise_id_to_type_map(language):
    """Cria um mapa definitivo de IDs de exercícios para seus tipos."""
    flashcards, gpt_exercicios = load_and_cache_data(language)
    id_para_tipo = {}
    for ex in gpt_exercicios:
        if ex.get('frase') and ex.get('tipo'):
            id_para_tipo[ex['frase']] = ex['tipo']
    for card in flashcards:
        if card.get("back"):
            id_para_tipo[f"significado::{card.get('back')}"] = "MCQ Significado"
            id_para_tipo[f"traducao::{card.get('back')}"] = "MCQ Tradução Inglês"
        if card.get("example"):
            id_para_tipo[f"fill::{card.get('example')}"] = "Fill"
            id_para_tipo[f"reading::{card.get('example')}"] = "Reading"
        if card.get("cloze_answer"):
            id_para_tipo[f"sinonimo::{card.get('cloze_answer')}"] = "MCQ Sinônimo"
    return id_para_tipo

def get_available_exercise_types_for_word(palavra, flashcards_map, gpt_exercicios_map):
    """Retorna um dicionário com todos os exercícios únicos para uma palavra."""
    exercicios_palavra = {}
    
    if palavra in flashcards_map:
        card = flashcards_map[palavra]
        if card.get("back"):
            exercicios_palavra[f"significado::{card.get('back')}"] = "MCQ Significado"
            exercicios_palavra[f"traducao::{card.get('back')}"] = "MCQ Tradução Inglês"
        if card.get("example"):
            exercicios_palavra[f"fill::{card.get('example')}"] = "Fill"
            exercicios_palavra[f"reading::{card.get('example')}"] = "Reading"
        if card.get("cloze_answer"):
            exercicios_palavra[f"sinonimo::{card.get('cloze_answer')}"] = "MCQ Sinônimo"
            
    if palavra in gpt_exercicios_map:
        for ex in gpt_exercicios_map[palavra]:
            if ex.get('frase') and ex.get('tipo'):
                exercicios_palavra[ex['frase']] = ex['tipo']
            
    return exercicios_palavra

def get_performance_summary(language):
    """Gera um resumo de desempenho do usuário."""
    print(f"DEBUG: Iniciando get_performance_summary para {language}...")
    db_df = get_session_db(language)
    historico = get_history(language)
    
    if db_df.empty:
        print("DEBUG: DataFrame de vocabulário vazio no summary. Retornando KPIs zerados.")
        return {
            "db_kpis": {'total': 0, 'ativas': 0, 'inativas': 0, 'anki': 0, 'gpt': 0},
            "kpis": {'precisao': "N/A", 'sessoes': 0, 'status_estudo': "N/A", 'divida_estudo': 0, 'progresso_divida': 0},
            "pie_data": {'Dominado': 0, 'Em Progresso': 0},
            "distribution_data": pd.Series(),
            "error_ranking": [],
            "age_ranking": []
        }

    kpis_db = {'total': len(db_df), 'ativas': len(db_df[db_df['ativa']]), 'inativas': len(db_df[~db_df['ativa']]), 'anki': len(db_df[db_df['fonte'] == 'ANKI']), 'gpt': len(db_df[db_df['fonte'] == 'GPT'])}
    
    historico_total = historico.get("quiz", []) + historico.get("gpt_quiz", []) + historico.get("mixed_quiz", [])
    total_acertos = sum(len(s.get("acertos", [])) for s in historico_total)
    total_erros = sum(len(s.get("erros", [])) for s in historico_total)
    total_testes = total_acertos + total_erros
    
    divida_estudo = (total_erros * 3) - total_acertos
    if divida_estudo <= 0:
        status_estudo = "Excelente!"; progresso_divida = 1.0; divida_estudo = 0
    else:
        status_estudo = "Atenção Necessária"; progresso_divida = total_acertos / (total_erros * 3) if total_erros > 0 else 1.0
    
    kpis_desempenho = {'precisao': f"{(total_acertos / total_testes * 100):.1f}%" if total_testes > 0 else "N/A", 'sessoes': len(historico_total), 'status_estudo': status_estudo, 'divida_estudo': divida_estudo, 'progresso_divida': progresso_divida}
    
    def calcular_progresso_geral(row):
        progresso_dict = row.get('progresso', {})
        if not isinstance(progresso_dict, dict) or not progresso_dict: return 0
        acertos_count = list(progresso_dict.values()).count('acerto')
        total_exercicios = len(progresso_dict)
        return (acertos_count / total_exercicios * 100) if total_exercicios > 0 else 0
    
    # Garante que 'data_adicao' é datetime antes de usar
    db_df['data_adicao'] = pd.to_datetime(db_df['data_adicao'], errors='coerce')
    db_df['progresso_percent'] = db_df.apply(calcular_progresso_geral, axis=1)
    mastered_count = len(db_df[db_df['progresso_percent'] >= 100])
    in_progress_count = len(db_df) - mastered_count
    bins = [-1, 0, 25, 50, 75, 101]
    labels = ['Não Iniciado', '1-25%', '26-50%', '51-75%', '76-100%']
    db_df['progress_bin'] = pd.cut(db_df['progresso_percent'], bins=bins, labels=labels, right=True)
    distribution_data = db_df['progress_bin'].value_counts().sort_index()
    
    mastery_pie_data = {'Dominado': mastered_count, 'Em Progresso': in_progress_count}
    
    all_errors = [word for s in historico_total for word in s.get("erros", [])]
    error_counts = Counter(all_errors)
    active_words_df = db_df[db_df['ativa']]
    active_words_set = set(active_words_df['palavra'])

    ranked_errors = []
    if not active_words_df.empty:
        word_to_date_map = active_words_df.set_index('palavra')['data_adicao'].to_dict()
        now = datetime.datetime.now(datetime.timezone.utc) # Usar timezone-aware datetime
        for word, count in error_counts.items():
            if word in active_words_set:
                creation_date = word_to_date_map.get(word)
                if pd.notna(creation_date):
                    # Garante que creation_date é timezone-aware ou naive como 'now'
                    if creation_date.tzinfo is None:
                        creation_date = creation_date.replace(tzinfo=datetime.timezone.utc)
                    days_since = (now - creation_date).days
                    ranked_errors.append((word, count, days_since))
    
    sorted_ranked_errors = sorted(ranked_errors, key=lambda item: item[1], reverse=True)

    age_ranking = []
    if not active_words_df.empty:
        now = datetime.datetime.now(datetime.timezone.utc) # Usar timezone-aware datetime
        for _, row in active_words_df.iterrows():
            word = row['palavra']
            creation_date = row['data_adicao']
            if pd.notna(creation_date):
                # Garante que creation_date é timezone-aware ou naive como 'now'
                if creation_date.tzinfo is None:
                    creation_date = creation_date.replace(tzinfo=datetime.timezone.utc)
                days_since = (now - creation_date).days
                age_ranking.append((word, days_since))
    
    sorted_age_ranking = sorted(age_ranking, key=lambda item: item[1], reverse=True)
    
    print(f"DEBUG: get_performance_summary finalizado para {language}.")
    return {
        "db_kpis": kpis_db, 
        "kpis": kpis_desempenho, 
        "pie_data": mastery_pie_data, 
        "distribution_data": distribution_data,
        "error_ranking": sorted_ranked_errors,
        "age_ranking": sorted_age_ranking
    }