import streamlit as st
import random
import re
from collections import defaultdict
from core.data_manager import (
    get_session_db, update_progress_from_quiz, load_and_cache_data,
    get_available_exercise_types_for_word, TIPOS_EXERCICIO_ANKI
)
from core.quiz_logic import gerar_questao_dinamica
from core.localization import get_text

def focus_quiz_ui(flashcards, gpt_exercicios, language, debug_mode):
    """
    Renderiza a página do Modo Foco, com depuração, tradução e exibição de nível CEFR.
    """
    if st.button(get_text("back_to_dashboard", language), key="back_from_focus"):
        st.session_state.current_page = "Homepage"
        st.session_state.pop('focus_quiz', None)
        st.rerun()

    st.header(get_text("focus_mode_button", language))
    
    db_df = get_session_db(language)
    palavras_ativas = sorted(db_df[db_df['ativa'] == True]['palavra'].tolist())
    
    flashcards_map = {card['front']: card for card in flashcards}
    gpt_exercicios_map = defaultdict(list)
    for ex in gpt_exercicios:
        principal = ex.get('principal')
        if isinstance(principal, str):
            gpt_exercicios_map[principal].append(ex)

    if debug_mode:
        st.subheader(f"Modo de Depuração Detalhado ({get_text('focus_mode_button', language)})")
        st.write("---")
        st.markdown(f"**1. Dados de Entrada:**")
        st.write(f"- Flashcards recebidos: `{len(flashcards)}`")
        st.write(f"- Exercícios GPT recebidos: `{len(gpt_exercicios)}`")
        st.markdown(f"**2. Palavras Ativas:**")
        st.write(f"- Total de palavras ativas encontradas: `{len(palavras_ativas)}`")
        with st.expander("Ver lista de palavras ativas"):
            st.write(palavras_ativas)
        st.divider()

    if not palavras_ativas:
        st.warning(get_text("no_active_words", language))
        return

    if 'focus_quiz' not in st.session_state:
        st.session_state.focus_quiz = {}

    if not st.session_state.focus_quiz.get('started', False):
        st.info(get_text("focus_mode_info", language))
        
        palavra_selecionada = st.selectbox(get_text("choose_focus_word", language), palavras_ativas)
        
        if st.button(get_text("start_focus_button", language, word=palavra_selecionada)):
            st.session_state.pop('focus_quiz', None)
            
            # CORREÇÃO: Usa a função com o nome correto
            exercicios_palavra = get_available_exercise_types_for_word(palavra_selecionada, flashcards_map, gpt_exercicios_map)
            
            playlist = [
                {'palavra': palavra_selecionada, 'tipo_exercicio': tipo, 'identificador': identificador}
                for identificador, tipo in exercicios_palavra.items() if tipo != '7-Cloze-Text'
            ]
            
            if not playlist:
                st.error(f"Nenhum exercício válido encontrado para a palavra '{palavra_selecionada}'.")
            else:
                random.shuffle(playlist)
                st.session_state.focus_quiz = {'started': True, 'playlist': playlist, 'idx': 0, 'resultados': [], 'mostrar_resposta': False}
                st.rerun()
    else:
        quiz = st.session_state.focus_quiz
        playlist = quiz.get('playlist', [])
        idx = quiz.get('idx', 0)

        if not quiz.get('started') or not playlist:
             st.warning("O quiz não pôde ser iniciado. Retornando à configuração.")
             st.session_state.pop('focus_quiz', None)
             st.rerun()

        total = len(playlist)
        if idx < total:
            if f"focus_pergunta_{idx}" not in st.session_state:
                item = playlist[idx]
                tipo, pergunta, opts, ans_idx, cefr_level, id_ex = gerar_questao_dinamica(item, flashcards, gpt_exercicios, db_df)
                st.session_state[f"focus_tipo_{idx}"] = tipo
                st.session_state[f"focus_pergunta_{idx}"] = pergunta
                st.session_state[f"focus_opts_{idx}"] = opts
                st.session_state[f"focus_ans_idx_{idx}"] = ans_idx
                st.session_state[f"focus_cefr_{idx}"] = cefr_level
                st.session_state[f"focus_id_ex_{idx}"] = id_ex
            
            tipo_interno, pergunta, opts, ans_idx, cefr_level, id_ex = (
                st.session_state.get(f"focus_tipo_{idx}"),
                st.session_state.get(f"focus_pergunta_{idx}"),
                st.session_state.get(f"focus_opts_{idx}"),
                st.session_state.get(f"focus_ans_idx_{idx}"),
                st.session_state.get(f"focus_cefr_{idx}"),
                st.session_state.get(f"focus_id_ex_{idx}")
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
                st.markdown(f"### {get_text('practicing_with', language)} <span class='keyword-highlight'>{playlist[0]['palavra']}</span>", unsafe_allow_html=True)
                st.progress(idx / total, get_text("quiz_progress", language).format(idx=idx, total=total))
                st.markdown(f'<div class="quiz-title">{tipo_display}</div>', unsafe_allow_html=True)
            with col2:
                if cefr_level:
                    st.markdown(f'<div style="text-align: right; font-weight: bold; font-size: 24px; color: #888;">{cefr_level}</div>', unsafe_allow_html=True)
            
            st.markdown(f'<div class="question-bg">{pergunta}</div>', unsafe_allow_html=True)
            
            with st.container():
                st.markdown('<div class="options-container">', unsafe_allow_html=True)
                resposta = st.radio("Selecione a resposta:", opts, key=f"focus_radio_{idx}", label_visibility="collapsed")
                st.markdown('</div>', unsafe_allow_html=True)

            col_btn1, col_btn2 = st.columns([3, 1])
            with col_btn1:
                if not quiz.get('mostrar_resposta'):
                    if st.button(get_text("check_button", language), key=f"focus_check_{idx}"):
                        quiz['mostrar_resposta'] = True
                        quiz['ultimo_resultado'] = (opts.index(resposta) == ans_idx)
                        quiz['ultimo_correto'] = opts[ans_idx]
                        st.rerun()
                else:
                    if st.button(get_text("next_button", language), key=f"focus_next_{idx}"):
                        resultado_str = "acerto" if quiz['ultimo_resultado'] else "erro"
                        item_atual = playlist[idx]
                        quiz['resultados'].append((item_atual['palavra'], resultado_str, id_ex, tipo_interno))
                        quiz['idx'] += 1
                        quiz['mostrar_resposta'] = False
                        st.rerun()
                    if quiz['ultimo_resultado']: st.success(get_text("correct_answer", language))
                    else: st.error(get_text("incorrect_answer", language).format(correct=quiz['ultimo_correto']))
            with col_btn2:
                if st.button(get_text("cancel_quiz", language)):
                    st.session_state.pop('focus_quiz', None)
                    st.rerun()
        else:
            update_progress_from_quiz(quiz.get('resultados', []), language)
            acertos = len([r for r in quiz.get('resultados', []) if r[1] == 'acerto'])
            erros = len(quiz.get('resultados', [])) - acertos
            score = int(acertos / total * 100) if total > 0 else 0
            st.success(get_text("final_result", language).format(correct_count=acertos, error_count=erros, score=score))
            
            if st.button(get_text("choose_another_word", language)):
                st.session_state.pop('focus_quiz', None)
                st.rerun()