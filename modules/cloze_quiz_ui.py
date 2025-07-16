import streamlit as st
import re
from core.data_manager import reset_quiz_state
from core.localization import get_text

def cloze_quiz_ui(gpt_exercicios, language, debug_mode):
    """
    Renderiza a página interativa do Cloze Quiz, com depuração, tradução e seleção de texto.
    """
    if st.button(get_text("back_to_dashboard", language), key="back_from_cloze"):
        st.session_state.current_page = "Homepage"
        st.session_state.pop('cloze_quiz', None)
        st.rerun()

    st.header(get_text("cloze_quiz_button", language))

    cloze_exercises = [ex for ex in gpt_exercicios if ex.get('tipo') == '7-Cloze-Text']

    # --- MODO DE DEPURAÇÃO ROBUSTO ---
    if debug_mode:
        st.subheader(f"Modo de Depuração Detalhado ({get_text('cloze_quiz_button', language)})")
        st.write("---")
        st.markdown(f"**1. Dados de Entrada:**")
        st.write(f"- Total de exercícios GPT recebidos (bruto): `{len(gpt_exercicios)}`")
        st.write(f"- Exercícios '7-Cloze-Text' encontrados após o filtro: `{len(cloze_exercises)}`")
        
        parsing_errors = st.session_state.get(f'parsing_errors_{language}', [])
        if any("Cloze" in error for error in parsing_errors):
            st.error("Erros detectados durante o carregamento do arquivo Cloze:")
            for error in parsing_errors:
                if "Cloze" in error: st.code(error)

        st.markdown("#### 2. Diagnóstico Final")
        if not gpt_exercicios:
             st.error("PROBLEMA DE CARREGAMENTO: Nenhum exercício GPT ou Cloze foi carregado. Verifique o log de erros na página de Estatísticas.")
        elif not cloze_exercises:
            st.error("PROBLEMA DE DADOS: Nenhum exercício do tipo '7-Cloze-Text' foi encontrado nos dados carregados. Verifique se as linhas correspondentes no arquivo `Dados_Manual_Cloze_text.txt` estão formatadas corretamente.")
        else:
            st.success("SUCESSO NA DEPURAÇÃO: Pelo menos um exercício Cloze foi carregado corretamente.")
        st.divider()

    if not cloze_exercises:
        st.warning(get_text("no_cloze_exercises_found", language))
        return

    nomes_exibicao = [ex.get('titulo', f"Texto Cloze #{i+1}") for i, ex in enumerate(cloze_exercises)]
    
    texto_selecionado_nome = st.selectbox(
        get_text("select_cloze_text", language),
        nomes_exibicao
    )
    
    exercicio_escolhido = next((ex for ex in cloze_exercises if ex.get('titulo') == texto_selecionado_nome), None)

    if not exercicio_escolhido:
        st.error("Não foi possível encontrar o exercício selecionado. Por favor, recarregue a página.")
        return

    respostas_corretas = exercicio_escolhido.get('correta', [])
    num_gaps = len(respostas_corretas)

    if 'cloze_quiz' not in st.session_state or st.session_state.cloze_quiz.get('id') != exercicio_escolhido['frase']:
        st.session_state.cloze_quiz = {
            'id': exercicio_escolhido['frase'], 'exercicio': exercicio_escolhido,
            'respostas': {}, 'submetido': False
        }
    
    quiz_state = st.session_state.cloze_quiz
    exercicio = quiz_state['exercicio']
    texto_original, opcoes_disponiveis = exercicio['frase'], exercicio['opcoes']
    
    st.info(get_text("cloze_info", language))
    
    respostas_usuario = quiz_state.get('respostas', {})
    placeholder = "---"
    opcoes_selecionaveis = [placeholder] + opcoes_disponiveis
    
    colunas_gaps = st.columns(num_gaps)
    
    for i in range(num_gaps):
        gap_index, gap_key = i + 1, f"gap_{i+1}"
        with colunas_gaps[i]:
            opcoes_usadas = [v for k, v in respostas_usuario.items() if k != gap_key and v != placeholder]
            opcoes_para_este_gap = [opt for opt in opcoes_selecionaveis if opt not in opcoes_usadas]
            
            selecao_atual = respostas_usuario.get(gap_key, placeholder)
            indice_selecao = opcoes_para_este_gap.index(selecao_atual) if selecao_atual in opcoes_para_este_gap else 0
            
            respostas_usuario[gap_key] = st.selectbox(f"GAP {gap_index}", opcoes_para_este_gap, index=indice_selecao, key=f"cloze_select_{gap_key}")

    partes_texto = re.split(r'(\[GAP\d+\])', texto_original)
    elementos_renderizados = []
    submetido = quiz_state.get('submetido', False)

    for parte in partes_texto:
        match = re.match(r'\[GAP(\d+)\]', parte)
        if match:
            gap_index = int(match.group(1))
            gap_key = f"gap_{gap_index}"
            resposta_selecionada = respostas_usuario.get(gap_key, placeholder)

            if submetido:
                resposta_correta_gap = respostas_corretas[gap_index - 1]
                if resposta_selecionada == resposta_correta_gap:
                    elementos_renderizados.append(f"<span style='color: green; font-weight: bold;'>{resposta_selecionada}</span>")
                else:
                    texto_exibido = resposta_selecionada if resposta_selecionada != placeholder else parte
                    elementos_renderizados.append(f"<span style='color: red; font-weight: bold;'>{texto_exibido}</span>")
            else:
                if resposta_selecionada != placeholder:
                    elementos_renderizados.append(f"<span style='color: blue; font-weight: bold;'>{resposta_selecionada}</span>")
                else:
                    elementos_renderizados.append(f"<span style='color: red;'>{parte}</span>")
        else:
            elementos_renderizados.append(parte)
    
    texto_com_respostas = "".join(elementos_renderizados)

    st.markdown(f"<div style='font-size: 1.2em;'>{texto_com_respostas}</div>", unsafe_allow_html=True)
    st.divider()

    col1, col2 = st.columns(2)
    if col1.button(get_text("check_answers_button", language), type="primary", use_container_width=True):
        quiz_state['submetido'] = True
        st.rerun()
    if col2.button(get_text("clear_answers_button", language), use_container_width=True):
        quiz_state['respostas'] = {}
        quiz_state['submetido'] = False
        st.rerun()

    if submetido:
        acertos = sum(1 for i in range(1, num_gaps + 1) if respostas_usuario.get(f"gap_{i}") == respostas_corretas[i-1])
        score = (acertos / num_gaps * 100) if num_gaps > 0 else 0
        st.success(f"Resultado: {acertos}/{num_gaps} acertos ({score:.0f}%)")
        if st.button(get_text("practice_another_text_button", language)):
            st.session_state.pop('cloze_quiz', None)
            st.rerun()