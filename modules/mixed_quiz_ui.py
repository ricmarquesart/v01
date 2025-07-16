import streamlit as st
import random
import datetime
import re
from collections import defaultdict
from core.data_manager import (
    get_session_db, get_history, save_history, reset_quiz_state, 
    update_progress_from_quiz, TIPOS_EXERCICIO_ANKI
)
from core.quiz_logic import selecionar_questoes_priorizadas, gerar_questao_dinamica
from core.localization import get_text

def mixed_quiz_ui(flashcards, gpt_exercicios, language, debug_mode):
    """
    Renderiza a página do Quiz Misto, com depuração, tradução e exibição de nível CEFR.
    """
    if st.button(get_text("back_to_dashboard", language), key="back_from_mixed"):
        st.session_state.current_page = "Homepage"
        st.session_state.pop('mixed_quiz', None)
        st.rerun()

    st.header(get_text("mixed_quiz_button", language))
    
    gpt_exercicios_filtrados = [ex for ex in gpt_exercicios if ex.get('tipo') != '7-Cloze-Text']
    db_df = get_session_db(language)

    if debug_mode:
        st.subheader(f"Modo de Depuração Detalhado ({get_text('mixed_quiz_button', language)})")
        st.write("---")
        st.markdown(f"**1. Dados de Entrada:**")
        st.write(f"- Flashcards ANKI recebidos: `{len(flashcards)}`")
        st.write(f"- Exercícios GPT (padrão) recebidos: `{len(gpt_exercicios_filtrados)}`")
        
        palavras_ativas_debug = db_df[db_df['ativa']]
        st.markdown(f"**2. Palavras Ativas:**")
        st.write(f"- Total de palavras ativas encontradas: `{len(palavras_ativas_debug)}`")

        st.markdown(f"**3. Geração da Playlist:**")
        flashcards_map_debug = {card['front']: card for card in flashcards}
        gpt_map_debug = defaultdict(list)
        for ex in gpt_exercicios_filtrados:
            if isinstance(ex.get('principal'), str):
                gpt_map_debug[ex['principal']].append(ex)
        
        playlist_debug = selecionar_questoes_priorizadas(palavras_ativas_debug, flashcards_map_debug, gpt_map_debug, 10)
        st.write(f"- Questões geradas para a playlist de depuração: `{len(playlist_debug)}`")
        with st.expander("Ver dados da playlist de depuração"):
            st.json(playlist_debug)
        
        st.markdown("#### 4. Diagnóstico Final")
        if (not flashcards and not gpt_exercicios_filtrados) or palavras_ativas_debug.empty or not playlist_debug:
             st.error("PROBLEMA CENTRAL DETECTADO: A playlist de questões está vazia. Verifique se os arquivos de dados foram carregados e se há palavras ativas com exercícios correspondentes.")
        else:
            st.success("SUCESSO NA DEPURAÇÃO: A playlist foi gerada corretamente.")
        st.divider()

    palavras_ativas = db_df[db_df['ativa'] == True]
    
    flashcards_map = {card['front']: card for card in flashcards}
    gpt_exercicios_map = defaultdict(list)
    for ex in gpt_exercicios_filtrados:
        if isinstance(ex.get('principal'), str):
            gpt_exercicios_map[ex['principal']].append(ex)

    if palavras_ativas.empty:
        st.warning(get_text("no_active_words", language))
        return

    if 'mixed_quiz' not in st.session_state:
        st.session_state.mixed_quiz = {}

    if not st.session_state.mixed_quiz.get('started', False):
        with st.form("mixed_quiz_cfg"):
            st.info(get_text("mixed_quiz_info", language))
            num_exercicios_disponiveis = len(palavras_ativas) * 8
            N = st.number_input(get_text("how_many_questions", language), 1, num_exercicios_disponiveis, min(10, num_exercicios_disponiveis), 1, key="mixed_n_cards")
            if st.form_submit_button(get_text("start_quiz", language)):
                reset_quiz_state("mixed_")
                playlist = selecionar_questoes_priorizadas(palavras_ativas, flashcards_map, gpt_exercicios_map, N)
                if not playlist:
                    st.error(get_text("no_valid_questions", language))
                else:
                    st.session_state.mixed_quiz = {
                        'started': True, 'playlist': playlist, 'idx': 0,
                        'resultados': [], 'mostrar_resposta': False
                    }
                    st.rerun()
    else:
        quiz_state = st.session_state.mixed_quiz
        playlist = quiz_state.get('playlist', [])
        idx = quiz_state.get('idx', 0)

        if not quiz_state.get('started') or not playlist:
             st.warning("O quiz não pôde ser iniciado. Retornando à configuração.")
             st.session_state.pop('mixed_quiz', None)
             st.rerun()

        total = len(playlist)
        if idx < total:
            if f"mixed_pergunta_{idx}" not in st.session_state:
                item_playlist = playlist[idx]
                tipo, pergunta, opts, ans_idx, cefr_level, id_ex = gerar_questao_dinamica(item_playlist, flashcards, gpt_exercicios, db_df)
                st.session_state[f"mixed_tipo_{idx}"] = tipo
                st.session_state[f"mixed_pergunta_{idx}"] = pergunta
                st.session_state[f"mixed_opts_{idx}"] = opts
                st.session_state[f"mixed_ans_idx_{idx}"] = ans_idx
                st.session_state[f"mixed_cefr_{idx}"] = cefr_level
                st.session_state[f"mixed_id_ex_{idx}"] = id_ex

            tipo_interno, pergunta, opts, ans_idx, cefr_level, id_ex = (
                st.session_state.get(f"mixed_tipo_{idx}"),
                st.session_state.get(f"mixed_pergunta_{idx}"),
                st.session_state.get(f"mixed_opts_{idx}"),
                st.session_state.get(f"mixed_ans_idx_{idx}"),
                st.session_state.get(f"mixed_cefr_{idx}"),
                st.session_state.get(f"mixed_id_ex_{idx}")
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
                quiz_state['idx'] += 1
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
                resposta = st.radio("Selecione a resposta:", opts, key=f"mixed_radio_{idx}", label_visibility="collapsed")
                st.markdown('</div>', unsafe_allow_html=True)

            col_btn1, col_btn2 = st.columns([3, 1])
            with col_btn1:
                if not quiz_state.get('mostrar_resposta'):
                    if st.button(get_text("check_button", language), key=f"mixed_check_{idx}"):
                        quiz_state['mostrar_resposta'] = True
                        quiz_state['ultimo_resultado'] = (opts.index(resposta) == ans_idx)
                        quiz_state['ultimo_correto'] = opts[ans_idx]
                        st.rerun()
                else:
                    if st.button(get_text("next_button", language), key=f"mixed_next_{idx}"):
                        item_atual = playlist[idx]
                        resultado_str = "acerto" if quiz_state['ultimo_resultado'] else "erro"
                        quiz_state['resultados'].append((item_atual['palavra'], resultado_str, id_ex, tipo_interno))
                        quiz_state['idx'] += 1
                        quiz_state['mostrar_resposta'] = False
                        st.rerun()
                    if quiz_state['ultimo_resultado']: st.success(get_text("correct_answer", language))
                    else: st.error(get_text("incorrect_answer", language).format(correct=quiz_state['ultimo_correto']))
            with col_btn2:
                if st.button(get_text("cancel_quiz", language)):
                    st.session_state.pop('mixed_quiz', None)
                    st.rerun()
        else:
            update_progress_from_quiz(quiz_state.get('resultados', []), language)
            acertos = [r[0] for r in quiz_state.get('resultados', []) if r[1] == 'acerto']
            erros = [r[0] for r in quiz_state.get('resultados', []) if r[1] == 'erro']
            score = int(len(acertos) / total * 100) if total > 0 else 0
            st.success(get_text("final_result", language).format(correct_count=len(acertos), error_count=len(erros), score=score))
            
            historico = get_history(language)
            historico.setdefault("mixed_quiz", []).append({
                "data": datetime.datetime.now().isoformat(),
                "acertos": acertos, "erros": erros, "score": score, "total": total
            })
            save_history(historico, language)
            
            if st.button(get_text("finish_button", language)):
                st.session_state.pop('mixed_quiz', None)
                st.rerun()