import streamlit as st
import random
import datetime
import pandas as pd
from core.data_manager import (
    save_history, get_session_db, reset_quiz_state, get_history,
    update_progress_from_quiz, TIPOS_EXERCICIO_ANKI
)
from core.quiz_logic import selecionar_questoes_priorizadas, gerar_questao_dinamica
from core.localization import get_text 

def quiz_ui(flashcards, gpt_exercicios, language, debug_mode):
    """
    Renderiza a página do Quiz ANKI, com modo de depuração robusto e interface traduzida.
    """
    if st.button(get_text("back_to_dashboard", language), key="back_from_anki"):
        st.session_state.current_page = "Homepage"
        st.session_state.pop('quiz_anki', None)
        st.rerun()

    st.header(get_text("anki_quiz_title", language))
    
    db_df = get_session_db(language)

    # CORREÇÃO DEFINITIVA: Verifica se o DataFrame não está vazio e se a coluna 'ativa' existe
    if not db_df.empty and 'ativa' in db_df.columns:
        palavras_ativas = db_df[db_df['ativa'] == True]
    else:
        palavras_ativas = pd.DataFrame(columns=db_df.columns)
    baralho_map = {card['front']: card for card in flashcards}

    tipos_legenda = {
        "MCQ Significado": get_text("word_meaning_anki", language),
        "MCQ Tradução Inglês": get_text("translation_anki", language),
        "MCQ Sinônimo": get_text("synonym_anki", language),
        "Fill": get_text("gap_fill_anki", language),
        "Reading": get_text("reading_anki", language)
    }

    if 'quiz_anki' not in st.session_state:
        st.session_state.quiz_anki = {}

    if not st.session_state.quiz_anki.get('started', False):
        with st.form("anki_quiz_cfg"):
            tipos_disponiveis = list(TIPOS_EXERCICIO_ANKI.keys())
            tipos_exibidos = ["Random"] + [tipos_legenda.get(t, t) for t in tipos_disponiveis]
            
            tipo_escolhido_leg = st.selectbox(get_text("choose_exercise_type", language), tipos_exibidos)
            
            max_questoes = sum(len(p.get('progresso', {})) for _, p in palavras_ativas.iterrows())
            N = st.number_input(get_text("how_many_questions", language), 1, max(1, max_questoes), min(10, max(1, max_questoes)), 1)
            
            if st.form_submit_button(get_text("start_quiz", language)):
                reset_quiz_state("quiz_anki_")
                tipo_escolhido_interno = {v: k for k, v in tipos_legenda.items()}.get(tipo_escolhido_leg, "Random")
                playlist = selecionar_questoes_priorizadas(palavras_ativas, baralho_map, {}, N, tipo_escolhido_interno)
                if not playlist:
                     st.error(get_text("no_valid_questions", language))
                else:
                    st.session_state.quiz_anki = {'started': True, 'idx': 0, 'total': len(playlist), 'playlist': playlist, 'resultados': []}
                    st.rerun()
    else:
        quiz = st.session_state.quiz_anki
        idx, total = quiz.get('idx', 0), quiz.get('total', 0)
        
        if not quiz.get('started') or not quiz.get('playlist'):
             st.warning("O quiz não pôde ser iniciado. Retornando à configuração.")
             st.session_state.pop('quiz_anki', None)
             st.rerun()

        if idx < total:
            if f"quiz_anki_pergunta_{idx}" not in st.session_state:
                item = quiz['playlist'][idx]
                tipo, pergunta, opts, ans_idx, cefr_level, id_ex = gerar_questao_dinamica(item, flashcards, gpt_exercicios, db_df)
                st.session_state[f"quiz_anki_tipo_{idx}"] = tipo
                st.session_state[f"quiz_anki_pergunta_{idx}"] = pergunta
                st.session_state[f"quiz_anki_opts_{idx}"] = opts
                st.session_state[f"quiz_anki_ans_idx_{idx}"] = ans_idx
                st.session_state[f"quiz_anki_cefr_{idx}"] = cefr_level
                st.session_state[f"quiz_anki_id_ex_{idx}"] = id_ex

            tipo_interno, pergunta, opts, ans_idx, cefr_level, id_ex = (
                st.session_state.get(f"quiz_anki_tipo_{idx}"),
                st.session_state.get(f"quiz_anki_pergunta_{idx}"),
                st.session_state.get(f"quiz_anki_opts_{idx}"),
                st.session_state.get(f"quiz_anki_ans_idx_{idx}"),
                st.session_state.get(f"quiz_anki_cefr_{idx}"),
                st.session_state.get(f"quiz_anki_id_ex_{idx}")
            )
            
            tipo_display = tipos_legenda.get(tipo_interno, tipo_interno)

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
                resposta = st.radio("Selecione a resposta:", opts, key=f"quiz_radio_{idx}", label_visibility="collapsed")
                st.markdown('</div>', unsafe_allow_html=True)

            col_btn1, col_btn2 = st.columns([3, 1])
            with col_btn1:
                if 'mostrar_resposta' not in quiz or not quiz['mostrar_resposta']:
                    if st.button(get_text("check_button", language), key=f"quiz_check_{idx}"):
                        quiz['mostrar_resposta'] = True
                        quiz['ultimo_resultado'] = (opts.index(resposta) == ans_idx)
                        quiz['ultimo_correto'] = opts[ans_idx]
                        st.rerun()
                else:
                    if st.button(get_text("next_button", language), key=f"quiz_next_{idx}"):
                        resultado_str = "acerto" if quiz['ultimo_resultado'] else "erro"
                        item_atual = quiz['playlist'][idx]
                        # Adiciona o tipo de exercício aos resultados para a atualização correta
                        quiz['resultados'].append((item_atual['palavra'], resultado_str, id_ex, tipo_interno))
                        quiz['idx'] += 1
                        quiz['mostrar_resposta'] = False
                        st.rerun()
                    if quiz['ultimo_resultado']: st.success(get_text("correct_answer", language))
                    else: st.error(get_text("incorrect_answer", language).format(correct=quiz['ultimo_correto']))
            with col_btn2:
                if st.button(get_text("cancel_quiz", language)):
                    st.session_state.pop('quiz_anki', None)
                    st.rerun()
        else:
            update_progress_from_quiz(quiz.get('resultados', []), language)
            if 'deactivated_words_notification' in st.session_state:
                deactivated_list = st.session_state['deactivated_words_notification']
                st.success(f"Parabéns! As seguintes palavras foram dominadas e desativadas: {', '.join(deactivated_list)}")
                del st.session_state['deactivated_words_notification']
            acertos = [r[0] for r in quiz.get('resultados', []) if r[1] == 'acerto']
            erros = [r[0] for r in quiz.get('resultados', []) if r[1] == 'erro']
            score = int(len(acertos) / total * 100) if total > 0 else 0
            st.success(get_text("final_result", language).format(correct_count=len(acertos), error_count=len(erros), score=score))
            historico = get_history(language)
            historico.setdefault("quiz", []).append({"data": datetime.datetime.now().isoformat(), "acertos": acertos, "erros": erros, "score": score, "total": total})
            save_history(historico, language)
            if st.button(get_text("finish_button", language)):
                st.session_state.pop('quiz_anki', None)
                st.rerun()