import streamlit as st
import random
import datetime
from collections import defaultdict
from core.data_manager import (
    get_session_db, save_history, reset_quiz_state, 
    update_progress_from_quiz, load_and_cache_data, save_vocab_db, TIPOS_EXERCICIO_ANKI
)
from core.quiz_logic import selecionar_questoes_priorizadas, gerar_questao_dinamica
from core.localization import get_text

def reactivate_words_on_error(words_to_reactivate, language):
    """
    Reativa palavras, zera seu progresso, mas mantém a contagem de domínio.
    """
    if not words_to_reactivate:
        return
    
    db_df = get_session_db(language)
    words_actually_reactivated = []

    for word in set(words_to_reactivate):
        idx_list = db_df.index[db_df['palavra'] == word].tolist()
        if not idx_list:
            continue
        
        idx = idx_list[0]
        
        db_df.loc[idx, 'ativa'] = True
        
        progresso = db_df.loc[idx, 'progresso']
        if isinstance(progresso, dict):
            for key in progresso:
                progresso[key] = 'nao_testado'
            db_df.loc[idx, 'progresso'] = progresso
        
        words_actually_reactivated.append(word)

    if words_actually_reactivated:
        save_vocab_db(db_df, language)
        st.session_state[f"db_df_{language}"] = db_df
        st.warning(get_text("words_reactivated", language).format(words=', '.join(words_actually_reactivated)))


def review_quiz_ui(flashcards, gpt_exercicios, language, debug_mode):
    """
    Renderiza a página do Modo de Revisão, com depuração, tradução e exibição de nível CEFR.
    """
    if st.button(get_text("back_to_dashboard", language), key="back_from_review"):
        st.session_state.current_page = "Homepage"
        st.session_state.pop('review_quiz', None)
        st.rerun()

    st.header(get_text("review_mode_title", language))
    
    gpt_exercicios_filtrados = [ex for ex in gpt_exercicios if ex.get('tipo') != '7-Cloze-Text']
    db_df = get_session_db(language)

    if debug_mode:
        st.subheader(f"Modo de Depuração Detalhado ({get_text('review_mode_title', language)})")
        st.write("---")
        palavras_inativas_debug = db_df[~db_df['ativa']]
        st.markdown(f"**1. Dados de Entrada:**")
        st.write(f"- Flashcards recebidos: `{len(flashcards)}`")
        st.write(f"- Exercícios GPT (padrão) recebidos: `{len(gpt_exercicios_filtrados)}`")
        st.write(f"- Total de palavras inativas (para revisão): `{len(palavras_inativas_debug)}`")
        st.divider()

    palavras_inativas = db_df[db_df['ativa'] == False]
    
    flashcards_map = {card['front']: card for card in flashcards}
    gpt_exercicios_map = defaultdict(list)
    for ex in gpt_exercicios_filtrados:
        if isinstance(ex.get('principal'), str):
            gpt_exercicios_map[ex['principal']].append(ex)

    if palavras_inativas.empty:
        st.info(get_text("no_inactive_words_info", language, default="You have no mastered words to review yet. Keep practicing in other modes!"))
        return

    if 'review_quiz' not in st.session_state:
        st.session_state.review_quiz = {}

    if not st.session_state.review_quiz.get('started', False):
        with st.form("review_quiz_cfg"):
            st.info(get_text("review_info", language))
            max_questoes = len(palavras_inativas)
            N = st.number_input(get_text("how_many_words_to_review", language), 1, max_questoes, min(5, max_questoes), 1)
            if st.form_submit_button(get_text("start_review", language)):
                reset_quiz_state("review_")
                playlist = selecionar_questoes_priorizadas(palavras_inativas, flashcards_map, gpt_exercicios_map, N)
                if not playlist:
                    st.error(get_text("no_valid_questions", language))
                else:
                    st.session_state.review_quiz = {'started': True, 'playlist': playlist, 'idx': 0, 'resultados': [], 'mostrar_resposta': False}
                    st.rerun()
    else:
        quiz = st.session_state.review_quiz
        playlist = quiz.get('playlist', [])
        idx = quiz.get('idx', 0)

        if not quiz.get('started') or not playlist:
             st.warning("O quiz não pôde ser iniciado. Retornando à configuração.")
             st.session_state.pop('review_quiz', None)
             st.rerun()

        total = len(playlist)
        if idx < total:
            if f"review_pergunta_{idx}" not in st.session_state:
                item = playlist[idx]
                tipo, pergunta, opts, ans_idx, cefr_level, id_ex = gerar_questao_dinamica(item, flashcards, gpt_exercicios, db_df)
                st.session_state[f"review_tipo_{idx}"] = tipo
                st.session_state[f"review_pergunta_{idx}"] = pergunta
                st.session_state[f"review_opts_{idx}"] = opts
                st.session_state[f"review_ans_idx_{idx}"] = ans_idx
                st.session_state[f"review_cefr_{idx}"] = cefr_level
                st.session_state[f"review_id_ex_{idx}"] = id_ex
            
            tipo_interno, pergunta, opts, ans_idx, cefr_level, id_ex = (
                st.session_state.get(f"review_tipo_{idx}"),
                st.session_state.get(f"review_pergunta_{idx}"),
                st.session_state.get(f"review_opts_{idx}"),
                st.session_state.get(f"review_ans_idx_{idx}"),
                st.session_state.get(f"review_cefr_{idx}"),
                st.session_state.get(f"review_id_ex_{idx}")
            )
            
            if tipo_interno in TIPOS_EXERCICIO_ANKI:
                tipos_legenda = {
                    "MCQ Significado": get_text("word_meaning_anki", language),
                    "MCQ Tradução Inglês": get_text("translation_anki", language),
                    "MCQ Sinônimo": get_text("synonym_anki", language),
                    "Fill": get_text("gap_fill_anki", language),
                    "Reading": get_text("reading_anki", language)
                }
                nome_base = tipos_legenda.get(tipo_interno, tipo_interno)
                tipo_display = f"{nome_base} (ANKI)"
            else:
                tipo_display = f"{tipo_interno} (GPT)"

            if not pergunta or opts is None:
                quiz['idx'] += 1
                st.rerun()

            col1, col2 = st.columns([4, 1])
            with col1:
                st.progress(idx / total, get_text("quiz_progress", language).format(idx=idx, total=total))
                st.markdown(f'<div class="quiz-title">{tipo_display}</div>', unsafe_allow_html=True)
            with col2:
                if cefr_level:
                    st.markdown(f'<div style="text-align: right; font-weight: bold; font-size: 24px; color: #888;">{cefr_level}</div>', unsafe_allow_html=True)
            
            st.markdown(f'<div class="question-bg">{pergunta}</div>', unsafe_allow_html=True)
            with st.container():
                st.markdown('<div class="options-container">', unsafe_allow_html=True)
                resposta = st.radio("Selecione a resposta:", opts, key=f"review_radio_{idx}", label_visibility="collapsed")
                st.markdown('</div>', unsafe_allow_html=True)

            col_btn1, col_btn2 = st.columns([3, 1])
            with col_btn1:
                if 'mostrar_resposta' not in quiz or not quiz['mostrar_resposta']:
                    if st.button(get_text("check_button", language), key=f"review_check_{idx}"):
                        quiz['mostrar_resposta'] = True
                        quiz['ultimo_resultado'] = (opts.index(resposta) == ans_idx)
                        quiz['ultimo_correto'] = opts[ans_idx]
                        st.rerun()
                else:
                    if st.button(get_text("next_button", language), key=f"review_next_{idx}"):
                        resultado_str = "acerto" if quiz['ultimo_resultado'] else "erro"
                        item_atual = playlist[idx]
                        quiz['resultados'].append((item_atual['palavra'], resultado_str, id_ex, tipo_interno))
                        quiz['idx'] += 1
                        quiz['mostrar_resposta'] = False
                        st.rerun()
                    if quiz['ultimo_resultado']: st.success(get_text("correct_answer", language))
                    else: st.error(get_text("incorrect_answer", language).format(correct=quiz['ultimo_correto']))
            with col_btn2:
                if st.button(get_text("cancel_review", language)):
                    st.session_state.pop('review_quiz', None)
                    st.rerun()
        else:
            erros = [r[0] for r in quiz.get('resultados', []) if r[1] == 'erro']
            reactivate_words_on_error(erros, language)
            
            acertos = [r[0] for r in quiz.get('resultados', []) if r[1] == 'acerto']
            score = int(len(acertos) / total * 100) if total > 0 else 0
            st.success(get_text("review_complete", language).format(score=score))
            
            if st.button(get_text("finish_button", language)):
                st.session_state.pop('review_quiz', None)
                st.rerun()