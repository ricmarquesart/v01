import streamlit as st
import random
import re
import datetime
from collections import defaultdict
import pandas as pd
from core.data_manager import (
    reset_quiz_state, save_history, get_session_db, get_history,
    update_progress_from_quiz, load_and_cache_data
)
from core.quiz_logic import selecionar_questoes_gpt
from core.localization import get_text

def gpt_ex_ui(gpt_exercicios, language, debug_mode):
    """
    Renderiza a página do Quiz GPT, com depuração, tradução e exibição de nível CEFR.
    """
    if st.button(get_text("back_to_dashboard", language), key="back_from_gpt"):
        st.session_state.current_page = "Homepage"
        st.session_state.pop('gpt_ex_quiz', None)
        st.rerun()

    st.header(get_text("gpt_quiz_title", language))
    
    gpt_exercicios_filtrados = [ex for ex in gpt_exercicios if ex.get('tipo') != '7-Cloze-Text']

    db_df = get_session_db(language)
    
    # CORREÇÃO DEFINITIVA: Verifica se o DataFrame não está vazio e se a coluna 'ativa' existe
    if not db_df.empty and 'ativa' in db_df.columns:
        palavras_ativas = db_df[db_df['ativa'] == True]
    else:
        palavras_ativas = pd.DataFrame(columns=db_df.columns)
    
    gpt_exercicios_map = defaultdict(list)
    for ex in gpt_exercicios_filtrados:
        if isinstance(ex.get('principal'), str):
            gpt_exercicios_map[ex['principal']].append(ex)

    if debug_mode:
        st.subheader(f"Modo de Depuração Detalhado ({get_text('gpt_quiz_button', language)})")
        st.write("---")
        st.markdown(f"**1. Dados de Entrada:**")
        st.write(f"- Total de exercícios GPT (bruto): `{len(gpt_exercicios)}`")
        st.write(f"- Exercícios GPT (padrão) recebidos: `{len(gpt_exercicios_filtrados)}`")
        
        parsing_errors = st.session_state.get(f'parsing_errors_{language}', [])
        if any("GPT" in error for error in parsing_errors):
            st.error("Erros detectados durante o carregamento dos dados GPT:")
            for error in parsing_errors:
                if "GPT" in error: st.code(error)
        
        if not db_df.empty and 'ativa' in db_df.columns:
            palavras_ativas_debug = db_df[db_df['ativa']]
        else:
            palavras_ativas_debug = pd.DataFrame(columns=db_df.columns)
        st.markdown(f"**2. Palavras Ativas:**")
        st.write(f"- Total de palavras ativas encontradas: `{len(palavras_ativas_debug)}`")

        st.markdown(f"**3. Mapeamento de Exercícios:**")
        st.write(f"- Total de palavras com exercícios GPT mapeados: `{len(gpt_exercicios_map)}`")

        palavras_prontas = sorted([p for p in gpt_exercicios_map if p in set(palavras_ativas_debug['palavra'].values)])
        st.markdown(f"**4. Cruzamento de Dados:**")
        st.write(f"- Total de palavras ativas que possuem exercícios GPT: `{len(palavras_prontas)}`")

        st.markdown("#### 5. Diagnóstico Final")
        if not gpt_exercicios_filtrados:
            st.error("PROBLEMA CENTRAL: Nenhum exercício GPT foi carregado.")
        elif not palavras_prontas:
            st.error("PROBLEMA CENTRAL: Nenhuma de suas palavras ativas tem um exercício GPT correspondente.")
        else:
            st.success("SUCESSO NA DEPURAÇÃO: A playlist deve ser gerada corretamente.")
        st.divider()

    if palavras_ativas.empty or not gpt_exercicios_map:
        st.warning(get_text("no_active_words", language))
        return

    if 'gpt_ex_quiz' not in st.session_state:
        st.session_state.gpt_ex_quiz = {}

    if not st.session_state.gpt_ex_quiz.get('started', False):
        with st.form("gpt_ex_cfg"):
            tipos_disponiveis = sorted(list(set(e['tipo'] for e_list in gpt_exercicios_map.values() for e in e_list)))
            tipos_exibidos = ["Random"] + tipos_disponiveis
            tipo_escolhido = st.selectbox(get_text("choose_exercise_type", language), tipos_exibidos)
            
            palavras_unicas_disponiveis = sorted([p for p in gpt_exercicios_map if p in set(palavras_ativas['palavra'].values)])
            
            if not palavras_unicas_disponiveis:
                st.warning("Nenhuma de suas palavras ativas possui exercícios GPT disponíveis.")
                st.form_submit_button(get_text("start_exercises", language), disabled=True)
            else:
                max_palavras = len(palavras_unicas_disponiveis)
                n_palavras = st.number_input(get_text("how_many_unique_words", language), 1, max_palavras, min(10, max_palavras), 1)
                repetir_palavra = st.radio(
                    get_text("allow_word_repetition", language), 
                    (get_text("option_no", language), get_text("option_yes", language)), 
                    index=0,
                    help=f"{get_text('repetition_help_no', language)} {get_text('repetition_help_yes', language)}"
                )

                if st.form_submit_button(get_text("start_exercises", language)):
                    reset_quiz_state("gpt_ex_")
                    playlist = selecionar_questoes_gpt(palavras_ativas, gpt_exercicios_map, tipo_escolhido, n_palavras, repetir_palavra == get_text("option_yes", language))
                    
                    if not playlist:
                        st.error(get_text("no_valid_questions", language))
                    else:
                        st.session_state.gpt_ex_quiz = {'started': True, 'playlist': playlist, 'idx': 0, 'resultados': [], 'show': False}
                        st.rerun()
    else:
        quiz_state = st.session_state.gpt_ex_quiz
        playlist = quiz_state.get('playlist', [])
        idx = quiz_state.get('idx', 0)
        
        if not quiz_state.get('started') or not playlist:
             st.warning("O quiz não pôde ser iniciado. Retornando à configuração.")
             st.session_state.pop('gpt_ex_quiz', None)
             st.rerun()

        total = len(playlist)
        if idx < total:
            ex = playlist[idx]
            tipo = ex.get('tipo')
            pergunta = ex.get('frase')
            opts_originais = ex.get('opcoes', [])
            correta = ex.get('correta')
            keyword = ex.get('principal')
            cefr_level = ex.get('cefr_level')

            tipos_para_filtrar_keyword = ["2-Word-Meaning", "3-Paraphrase", "4-Minimal-Pair"]
            if tipo in tipos_para_filtrar_keyword:
                opcoes_filtradas = [opt for opt in opts_originais if opt.lower() != keyword.lower()]
            else:
                opcoes_filtradas = opts_originais
            opts = list(set(opcoes_filtradas))
            if len(opts) < 4:
                necessarios = 4 - len(opts)
                palavras_existentes = {opt.lower() for opt in opts}
                palavras_existentes.add(keyword.lower())
                palavras_existentes.add(correta.lower())
                pool_distratores = [p for p in db_df['palavra'].tolist() if p.lower() not in palavras_existentes]
                if len(pool_distratores) >= necessarios:
                    novos_distratores = random.sample(pool_distratores, k=necessarios)
                    opts.extend(novos_distratores)

            col1, col2 = st.columns([4, 1])
            with col1:
                st.progress(idx / total, get_text("quiz_progress", language).format(idx=idx, total=total))
                st.markdown(f'<div class="quiz-title">{tipo}</div>', unsafe_allow_html=True)
            with col2:
                if cefr_level:
                    st.markdown(f'<div style="text-align: right; font-weight: bold; font-size: 24px; color: #888;">{cefr_level}</div>', unsafe_allow_html=True)

            frase_html = re.sub(rf'{re.escape(ex["principal"])}', f'<span class="keyword-highlight">{ex["principal"]}</span>', pergunta, flags=re.IGNORECASE)
            st.markdown(f'<div class="question-bg">{frase_html}</div>', unsafe_allow_html=True)

            with st.container():
                st.markdown('<div class="options-container">', unsafe_allow_html=True)
                if f"gpt_ex_opts_{idx}" not in st.session_state:
                    random.shuffle(opts)
                    st.session_state[f"gpt_ex_opts_{idx}"] = opts
                
                if correta not in st.session_state[f"gpt_ex_opts_{idx}"]:
                    quiz_state['idx'] += 1
                    st.rerun()

                resposta = st.radio("", st.session_state[f"gpt_ex_opts_{idx}"], key=f"gpt_ex_radio_{idx}", label_visibility="collapsed")
                st.markdown('</div>', unsafe_allow_html=True)
            
            col_btn1, col_btn2 = st.columns([3, 1])
            with col_btn1:
                if not quiz_state.get('show'):
                    if st.button(get_text("check_button", language), key=f"gpt_ex_check_{idx}"):
                        quiz_state['show'] = True
                        quiz_state['ultimo_resultado'] = (resposta == correta)
                        quiz_state['ultimo_correto'] = correta
                        st.rerun()
                else:
                    if st.button(get_text("next_button", language), key=f"gpt_ex_next_{idx}"):
                        resultado_str = "acerto" if quiz_state['ultimo_resultado'] else "erro"
                        # --- CORREÇÃO ---
                        # Adiciona as 4 informações necessárias para o registo de progresso
                        quiz_state['resultados'].append((ex["principal"], resultado_str, ex['frase'], ex['tipo']))
                        quiz_state['idx'] += 1
                        quiz_state['show'] = False
                        st.rerun()
                    if quiz_state['ultimo_resultado']: st.success(get_text("correct_answer", language))
                    else: st.error(get_text("incorrect_answer", language).format(correct=quiz_state['ultimo_correto']))
            with col_btn2:
                if st.button(get_text("cancel_exercises", language)): 
                    st.session_state.pop('gpt_ex_quiz', None)
                    st.rerun()
        else:
            update_progress_from_quiz(quiz_state.get('resultados', []), language)
            acertos = [r[0] for r in quiz_state.get('resultados', []) if r[1] == 'acerto']
            erros = [r[0] for r in quiz_state.get('resultados', []) if r[1] == 'erro']
            score = int(len(acertos) / total * 100) if total > 0 else 0
            st.success(get_text("final_result", language).format(correct_count=len(acertos), error_count=len(erros), score=score))
            
            historico = get_history(language)
            historico.setdefault("gpt_quiz", []).append({
                "data": datetime.datetime.now().isoformat(), 
                "acertos": acertos, "erros": erros, "score": score, "total": total
            })
            save_history(historico, language)
            
            if st.button(get_text("finish_button", language)): 
                st.session_state.pop('gpt_ex_quiz', None)
                st.rerun()