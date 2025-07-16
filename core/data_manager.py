import os
import json
import re
import streamlit as st
import pandas as pd
import datetime
from collections import Counter, defaultdict
import random

# --- Constantes ---
CARTOES_FILE_BASE = 'cartoes_validacao.txt'
GPT_FILE_BASE = 'Dados_Manual_output_GPT.txt'
CLOZE_FILE_BASE = 'Dados_Manual_Cloze_text.txt'
DB_FILE_BASE = 'vocab_database'
WRITING_LOG_FILE_BASE = 'writing_log'
HISTORICO_FILE_BASE = 'historico'
SENTENCE_WORDS_FILE = 'palavras_unicas_por_tipo.txt'
SENTENCE_LOG_FILE_BASE = 'sentence_log'


# --- Classes de Erro Personalizadas ---
class ParsingError(Exception):
    """Exceção para erros durante o parsing de ficheiros de dados."""
    pass

# --- GERADORES DE QUESTÕES (CENTRALIZADOS) ---
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

@st.cache_data
def load_and_cache_data(language):
    flashcards, anki_errors = carregar_flashcards_from_file(language)
    gpt_exercicios, gpt_errors = carregar_gpt_from_file(language)
    cloze_exercicios, cloze_errors = carregar_cloze_from_file(language)
    
    todos_exercicios = gpt_exercicios + cloze_exercicios
    errors = anki_errors + gpt_errors + cloze_errors
    
    st.session_state[f'parsing_errors_{language}'] = errors
    return flashcards, todos_exercicios

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

def get_lang_filename(base_name, language, extension=None):
    lang_suffix = "_en" if language == 'en' else "_fr"
    if extension is None:
        extension = ".json"
    return f"{base_name}{lang_suffix}{extension}"

def carregar_flashcards_from_file(language):
    filepath = CARTOES_FILE_BASE
    if not os.path.exists(filepath):
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
    return flashcards, errors

def carregar_gpt_from_file(language):
    gpt_file = GPT_FILE_BASE
    if not os.path.exists(gpt_file):
        return [], [f"Arquivo de exercícios GPT não encontrado. Caminho verificado: '{os.path.abspath(gpt_file)}'"]

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
            if idioma_linha != language:
                continue

            if not tipo.startswith(('1-', '2-', '3-', '4-', '5-', '6-')):
                continue
            
            if not all([tipo, frase, opcoes_str, correta, principal, cefr_level]):
                raise ParsingError("Uma das colunas obrigatórias está vazia.")
            
            opcoes_lista = [o.strip() for o in opcoes_str.split('|')]
            if not opcoes_lista or not all(opcoes_lista):
                raise ParsingError("Opções inválidas.")
            
            exercicios.append({"tipo": tipo, "frase": frase, "opcoes": opcoes_lista, "correta": correta, "principal": principal, "cefr_level": cefr_level})
        except Exception as e:
            errors.append(f"Erro ao processar linha GPT #{i+1} ('{linha[:40]}...'): {e}")
    return exercicios, errors

def carregar_cloze_from_file(language):
    cloze_file = CLOZE_FILE_BASE
    if not os.path.exists(cloze_file):
        return [], [f"Arquivo Cloze não encontrado. Caminho verificado: '{os.path.abspath(cloze_file)}'"]

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
            
            if idioma_linha != language or tipo != '7-Cloze-Text':
                continue

            opcoes_lista = [o.strip() for o in opcoes_str.split('|')]
            corretas_lista = [c.strip() for c in corretas_str.split('|')]
            
            principais_lista = corretas_lista
            
            exercicios.append({
                "tipo": tipo, "frase": frase, "opcoes": opcoes_lista, 
                "correta": corretas_lista, "principal": principais_lista, 
                "cefr_level": cefr_level, "titulo": titulo
            })
        except Exception as e:
            errors.append(f"Erro ao processar linha Cloze #{i+1} ('{linha[:40]}...'): {e}")
    return exercicios, errors


def get_session_db(language):
    session_key = f"db_df_{language}"
    if session_key not in st.session_state:
        st.session_state[session_key] = sync_database(language)
    return st.session_state[session_key]

def sync_database(language):
    db_file = get_lang_filename(DB_FILE_BASE, language)
    
    if os.path.exists(db_file) and os.path.getsize(db_file) > 2:
        try:
            db_df = pd.read_json(db_file)
        except ValueError:
            db_df = pd.DataFrame()
    else: 
        db_df = pd.DataFrame()

    if not db_df.empty and 'palavra' in db_df.columns:
        db_df = db_df[~db_df['palavra'].str.contains(',', na=False, case=False)]
    
    required_cols = {
        "palavra": object, "ativa": bool, "fonte": object, 
        "data_adicao": 'datetime64[ns]', "escrita_completa": bool, 
        "progresso": object, "mastery_count": int
    }
    
    for col, dtype in required_cols.items():
        if col not in db_df.columns:
            if dtype == bool:
                db_df[col] = True if col == 'ativa' else False
            elif dtype == int:
                db_df[col] = 0
            else:
                db_df[col] = pd.NA if dtype == 'datetime64[ns]' else None
    
    flashcards, gpt_exercicios = load_and_cache_data(language)
    flashcards_map = {card['front']: card for card in flashcards}
    gpt_exercicios_map = defaultdict(list)
    palavras_gpt = set()
    for ex in gpt_exercicios:
        if ex.get('tipo') == '7-Cloze-Text':
            continue
        principais = ex['principal'] if isinstance(ex['principal'], list) else [ex['principal']]
        for p in principais:
            gpt_exercicios_map[p].append(ex)
            palavras_gpt.add(p)
            
    if not db_df.empty:
        for index, row in db_df.iterrows():
            palavra = row['palavra']
            progresso_antigo = row.get('progresso', {})
            if not isinstance(progresso_antigo, dict): progresso_antigo = {}
            exercicios_atuais = get_available_exercise_types_for_word(palavra, flashcards_map, gpt_exercicios_map)
            progresso_novo = {id_ex: progresso_antigo.get(id_ex, "nao_testado") for id_ex in exercicios_atuais}
            db_df.at[index, 'progresso'] = progresso_novo

    todas_palavras = set(flashcards_map.keys()).union(palavras_gpt)
    palavras_db = set(db_df['palavra']) if 'palavra' in db_df.columns else set()
    novas_palavras = todas_palavras - palavras_db
    
    if novas_palavras:
        now = datetime.datetime.now().isoformat()
        novos_dados = []
        for p in novas_palavras:
            fonte = "ANKI" if p in flashcards_map else "GPT"
            exercicios_palavra = get_available_exercise_types_for_word(p, flashcards_map, gpt_exercicios_map)
            progresso = {identificador: "nao_testado" for identificador in exercicios_palavra.keys()}
            novos_dados.append({"palavra": p, "ativa": True, "fonte": fonte, "data_adicao": now, "escrita_completa": False, "progresso": progresso, "mastery_count": 0})
        if novos_dados:
            novos_df = pd.DataFrame(novos_dados)
            db_df = pd.concat([db_df, novos_df], ignore_index=True) if not db_df.empty else novos_df
            
    if 'mastery_count' not in db_df.columns:
        db_df['mastery_count'] = 0
    db_df['mastery_count'] = db_df['mastery_count'].fillna(0).astype(int)
    
    save_vocab_db(db_df, language)
    return db_df

def save_vocab_db(df, language):
    db_file = get_lang_filename(DB_FILE_BASE, language)
    if 'progresso' not in df.columns: df['progresso'] = [{} for _ in range(len(df))]
    df['progresso'] = df['progresso'].apply(lambda x: x if isinstance(x, dict) else {})
    if 'mastery_count' not in df.columns: df['mastery_count'] = 0
    df['mastery_count'] = df['mastery_count'].fillna(0).astype(int)
    df.to_json(db_file, orient='records', indent=4)

def get_history(language):
    hist_file = get_lang_filename(HISTORICO_FILE_BASE, language)
    if os.path.exists(hist_file):
        try:
            with open(hist_file, 'r', encoding='utf-8') as f: return json.load(f)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return {"quiz": [], "gpt_quiz": [], "mixed_quiz": []}
    return {"quiz": [], "gpt_quiz": [], "mixed_quiz": []}

def save_history(historico, language):
    hist_file = get_lang_filename(HISTORICO_FILE_BASE, language)
    with open(hist_file, 'w', encoding='utf-8') as f: json.dump(historico, f, indent=4)

def update_progress_from_quiz(quiz_results, language):
    db_df = get_session_db(language)
    if 'mastery_count' not in db_df.columns:
        db_df['mastery_count'] = 0
    db_df['mastery_count'] = db_df['mastery_count'].fillna(0)
    deactivated_words = []
    
    for palavra, resultado, identificador_exercicio, tipo_exercicio in quiz_results:
        idx_list = db_df.index[db_df['palavra'] == palavra].tolist()
        if not idx_list: continue
        idx = idx_list[0]
        progresso = db_df.at[idx, 'progresso']
        if not isinstance(progresso, dict): progresso = {}
        
        if identificador_exercicio in progresso:
            if resultado == "acerto":
                progresso[identificador_exercicio] = "acerto"
            elif resultado == "erro":
                progresso[identificador_exercicio] = "erro"
            
        db_df.at[idx, 'progresso'] = progresso
        
        if all(status == 'acerto' for status in progresso.values()):
            if db_df.at[idx, 'ativa']:
                db_df.at[idx, 'ativa'] = False
                db_df.at[idx, 'mastery_count'] = int(db_df.at[idx, 'mastery_count'] + 1)
                deactivated_words.append(palavra)
                
    save_vocab_db(db_df, language)
    st.session_state[f"db_df_{language}"] = db_df
    if deactivated_words: st.session_state['deactivated_words_notification'] = deactivated_words

def clear_history(language):
    hist_file = get_lang_filename(HISTORICO_FILE_BASE, language)
    empty_history = {"quiz": [], "gpt_quiz": [], "mixed_quiz": []}
    with open(hist_file, 'w') as f: json.dump(empty_history, f, indent=4)
    st.success("Histórico de desempenho foi limpo com sucesso!")

def get_writing_log(language):
    log_file = get_lang_filename(WRITING_LOG_FILE_BASE, language)
    if not os.path.exists(log_file): return []
    with open(log_file, 'r', encoding='utf-8') as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return []

def add_writing_entry(entry, language):
    log = get_writing_log(language)
    log.append(entry)
    log_file = get_lang_filename(WRITING_LOG_FILE_BASE, language)
    with open(log_file, 'w', encoding='utf-8') as f: json.dump(log, f, indent=4)
    db_df = get_session_db(language)
    db_df.loc[db_df['palavra'] == entry['palavra'], 'escrita_completa'] = True
    save_vocab_db(db_df, language)

def delete_writing_entries(entries_to_delete, language):
    log = get_writing_log(language)
    ids_to_delete = {json.dumps(entry, sort_keys=True) for entry in entries_to_delete}
    updated_log = [entry for entry in log if json.dumps(entry, sort_keys=True) not in ids_to_delete]
    log_file = get_lang_filename(WRITING_LOG_FILE_BASE, language)
    with open(log_file, 'w') as f: json.dump(updated_log, f, indent=4)

def delete_cloze_exercises(exercises_to_delete, language):
    gpt_file = CLOZE_FILE_BASE
    if not os.path.exists(gpt_file): return
    phrases_to_delete = {ex['frase'] for ex in exercises_to_delete}
    with open(gpt_file, 'r', encoding='utf-8') as f:
        linhas = f.readlines()
    linhas_mantidas = []
    for linha in linhas:
        try:
            partes = linha.strip().split(';')
            if len(partes) > 2 and partes[0].strip() == language and partes[1].strip() == '7-Cloze-Text':
                frase_da_linha = partes[2].strip()
                if frase_da_linha not in phrases_to_delete:
                    linhas_mantidas.append(linha)
            else:
                linhas_mantidas.append(linha)
        except IndexError:
            linhas_mantidas.append(linha)
    with open(gpt_file, 'w', encoding='utf-8') as f: f.writelines(linhas_mantidas)

def reset_quiz_state(prefix):
    keys_to_del = [k for k in st.session_state.keys() if k.startswith(prefix)]
    for k in keys_to_del:
        del st.session_state[k]

def get_performance_summary(language):
    db_df = sync_database(language)
    historico = get_history(language)
    
    if db_df.empty:
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
        now = datetime.datetime.now()
        for word, count in error_counts.items():
            if word in active_words_set:
                creation_date = word_to_date_map.get(word)
                if pd.notna(creation_date) and creation_date.tzinfo is not None:
                    creation_date = creation_date.tz_localize(None)
                if pd.notna(creation_date):
                    days_since = (now - creation_date).days
                    ranked_errors.append((word, count, days_since))
    
    sorted_ranked_errors = sorted(ranked_errors, key=lambda item: item[1], reverse=True)

    age_ranking = []
    if not active_words_df.empty:
        now = datetime.datetime.now()
        for _, row in active_words_df.iterrows():
            word = row['palavra']
            creation_date = row['data_adicao']
            if pd.notna(creation_date) and creation_date.tzinfo is not None:
                creation_date = creation_date.tz_localize(None)
            if pd.notna(creation_date):
                days_since = (now - creation_date).days
                age_ranking.append((word, days_since))
    
    sorted_age_ranking = sorted(age_ranking, key=lambda item: item[1], reverse=True)
    
    return {
        "db_kpis": kpis_db, 
        "kpis": kpis_desempenho, 
        "pie_data": mastery_pie_data, 
        "distribution_data": distribution_data,
        "error_ranking": sorted_ranked_errors,
        "age_ranking": sorted_age_ranking
    }

def load_sentence_data(language):
    """Carrega as palavras e metadados do ficheiro de frases."""
    if not os.path.exists(SENTENCE_WORDS_FILE):
        return {}
    
    with open(SENTENCE_WORDS_FILE, 'r', encoding='utf-8') as f:
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
                chave = chave.strip().lstrip('-').strip()
                dados[chave] = valor.strip()

        if palavra and dados.get("Tipo de Nota") == target_note_type:
            classe = dados.get('Classe', 'N/A')
            unique_key = f"{palavra} ({classe})"
            dados['palavra_base'] = palavra
            words_data[unique_key] = dados
            
    return words_data

def load_sentence_log(language):
    """Carrega o log de frases escritas pelo utilizador."""
    log_file = get_lang_filename(SENTENCE_LOG_FILE_BASE, language)
    if not os.path.exists(log_file):
        return []
    with open(log_file, 'r', encoding='utf-8') as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return []

def save_sentence_log(log_data, language):
    """Salva o log de frases escritas pelo utilizador."""
    log_file = get_lang_filename(SENTENCE_LOG_FILE_BASE, language)
    with open(log_file, 'w', encoding='utf-8') as f:
        json.dump(log_data, f, indent=4, ensure_ascii=False)

def delete_sentence_log_entry(word_key, language):
    """Apaga uma entrada específica do log de frases."""
    log_data = load_sentence_log(language)
    log_atualizado = [entry for entry in log_data if entry.get('palavra_chave') != word_key]
    save_sentence_log(log_atualizado, language)