from flask import Blueprint, request, jsonify
from flask_cors import cross_origin
import requests
from bs4 import BeautifulSoup
import csv
import io
import pypdf
import re
import unicodedata
from datetime import datetime, timedelta
import time

validador_bp = Blueprint('validador', __name__)

# --- Funções de Ajuda e Normalização ---

def normalize_string(text):
    if not isinstance(text, str):
        return ""
    text = text.lower()
    text = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('utf-8')
    text = re.sub(r'[^a-z0-9\s]', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def normalize_cnpj(cnpj_str):
    if not isinstance(cnpj_str, str):
        return ""
    cnpj_numeros = re.sub(r'\D', '', cnpj_str)
    return cnpj_numeros.strip()

def extract_and_normalize_date(text_content):
    meses = {
        'janeiro': '01', 'fevereiro': '02', 'março': '03', 'abril': '04',
        'maio': '05', 'junho': '06', 'julho': '07', 'agosto': '08',
        'setembro': '09', 'outubro': '10', 'novembro': '11', 'dezembro': '12'
    }
    
    date_pattern_extenso = re.compile(
        r'(\d{1,2})\s+de\s+([a-zA-ZçÇ]+)\s+de\s+(\d{4})', 
        re.IGNORECASE
    )
    
    match = date_pattern_extenso.search(text_content)
    if match:
        day = match.group(1)
        month_extenso = match.group(2).lower()
        year = match.group(3)
        
        month_num = meses.get(month_extenso)
        if month_num:
            try:
                day_padded = day.zfill(2)
                date_str = f"{day_padded}/{month_num}/{year}"
                return datetime.strptime(date_str, '%d/%m/%Y')
            except ValueError:
                return None
    
    date_pattern_numerico = re.compile(r'(\d{1,2})[/-](\d{1,2})[/-](\d{4})')
    match_num = date_pattern_numerico.search(text_content)
    if match_num:
        day, month, year = match_num.groups()
        try:
            date_str = f"{day.zfill(2)}/{month.zfill(2)}/{year}"
            return datetime.strptime(date_str, '%d/%m/%Y')
        except ValueError:
            return None
            
    return None

# --- Funções de Extração de Dados do Documento ---

def get_document_content(document_url):
    try:
        response = requests.get(document_url, timeout=30)
        response.raise_for_status()

        content_type = response.headers.get('Content-Type', '')
        raw_text_content = ""
        doc_type = "unknown"

        if 'application/pdf' in content_type or document_url.lower().endswith('.pdf'):
            pdf_file = io.BytesIO(response.content)
            reader = pypdf.PdfReader(pdf_file)
            for page in reader.pages:
                raw_text_content += page.extract_text() or ""
            doc_type = "pdf"
        else:
            soup = BeautifulSoup(response.text, 'html.parser')
            raw_text_content = soup.get_text()
            doc_type = "html"
        
        return raw_text_content, doc_type, None

    except requests.exceptions.RequestException as e:
        return None, None, f"Erro ao acessar o documento: {e}"
    except pypdf.errors.PdfReadError as e:
        return None, None, f"Erro ao ler o arquivo PDF. Pode ser corrompido ou protegido: {e}"
    except Exception as e:
        return None, None, f"Erro ao processar o documento: {e}"

def extract_cnpj_from_document(document_url, raw_text_content):
    cnpj = None
    cnpj_url_match = re.findall(r'(\d{14})\.(?:pdf|html|txt)', document_url, re.IGNORECASE)
    if cnpj_url_match:
        cnpj = normalize_cnpj(cnpj_url_match[-1])
    else:
        if raw_text_content:
            cnpj_pattern = re.compile(
                r'CN\s*PJ\s*(?:nº|n\.|no|:)?\s*(\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}|\d{14})', 
                re.IGNORECASE
            )
            cnpj_match = cnpj_pattern.search(raw_text_content)
            if cnpj_match:
                cnpj = normalize_cnpj(cnpj_match.group(1))
    return cnpj

def extract_legal_representative_from_eu(raw_text_content):
    representante_legal = None
    start_index_eu = raw_text_content.find("Eu,")
    if start_index_eu != -1:
        substring_after_eu = raw_text_content[start_index_eu + len("Eu,"):].strip()
        end_name_index = -1
        if substring_after_eu:
            delimiters = [',', '.', '\n', '(', ')', '[', ']', '-', '\r', ' e ', ' ou ', ' inscrito no '] 
            found_indices = [substring_after_eu.lower().find(d) for d in delimiters if substring_after_eu.lower().find(d) != -1]
            if found_indices:
                end_name_index = min(found_indices)
        if end_name_index != -1:
            representante_legal = substring_after_eu[:end_name_index].strip()
        else:
            representante_legal = substring_after_eu.split('\n')[0].strip()
            if len(representante_legal) > 100:
                representante_legal = representante_legal[:100].strip() + "..." 
        representante_legal = representante_legal.replace('"', '').replace("'", '').strip()
    return representante_legal

def check_specific_names_presence_in_pdf(raw_text_content, specific_names_list_from_sheet):
    if not raw_text_content or not specific_names_list_from_sheet:
        return None

    text_content_normalized = normalize_string(raw_text_content)
    
    for original_name in specific_names_list_from_sheet:
        normalized_name = normalize_string(original_name)
        if normalized_name in text_content_normalized:
            return original_name
    return None

def consultar_cnpj_receita_federal(cnpj):
    cnpj = ''.join(filter(str.isdigit, cnpj))
    url = f"https://www.receitaws.com.br/v1/cnpj/{cnpj}"
    
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        
        dados_cnpj = response.json()
        
        if dados_cnpj.get('status') == 'ERROR':
            return None
            
        time.sleep(1)  # Rate limiting
        return dados_cnpj
        
    except Exception as e:
        return None

# --- Rotas da API ---

@validador_bp.route('/carregar-planilha', methods=['POST', 'GET'])
@cross_origin()
def carregar_planilha():
    """Carrega e processa a planilha CSV do Google Sheets via URL Fixa"""
    try:
        csv_url = "https://docs.google.com/spreadsheets/d/e/2PACX-1vStbYGz6Lq-6ZBrCawbKxItY-OzTTLABh-iS1efLY5WZgREDNeJNkH9J23peyde89H7lzzm8tPYQymA/pub?output=csv"
        
        response = requests.get(csv_url, timeout=30)
        response.raise_for_status()
        
        csv_content = response.text
        csv_reader = csv.reader(io.StringIO(csv_content))
        
        razoes_sociais_planilha = []
        cnpjs_planilha = []
        cnpj_para_nome_coluna_k_map = {}
        responsavel_rede_planilha = []
        
        for row_index, row in enumerate(csv_reader):
            if row_index == 0:  
                continue
                
            if len(row) > 2:  # Coluna C
                cnpj_celula = row[2].strip()
                if cnpj_celula and cnpj_celula.upper() != '#N/A':
                    cnpjs_planilha.append(cnpj_celula)
            
            if len(row) > 3:  # Coluna D
                razao_social_celula = row[3].strip()
                if razao_social_celula and razao_social_celula.upper() != '#N/A':
                    razoes_sociais_planilha.append(razao_social_celula)
            
            if len(row) > 10:  # Coluna K
                nome_representante_celula = row[10].strip()
                if nome_representante_celula and nome_representante_celula.upper() != '#N/A':
                    if len(row) > 2:
                        cnpj_celula = row[2].strip()
                        if cnpj_celula and cnpj_celula.upper() != '#N/A':
                            cnpj_para_nome_coluna_k_map[cnpj_celula] = nome_representante_celula
            
            if len(row) > 11:  # Coluna L
                nomes_em_celula = row[11].strip()
                if nomes_em_celula and nomes_em_celula.upper() != '#N/A':
                    nomes_divididos = [nome.strip() for nome in nomes_em_celula.split(',')]
                    nomes_validos = [nome for nome in nomes_divididos if nome and nome.upper() != '#N/A']
                    responsavel_rede_planilha.extend(nomes_validos)
        
        return jsonify({
            'success': True,
            'dados': {
                'razoes_sociais': len(razoes_sociais_planilha),
                'cnpjs': len(cnpjs_planilha),
                'representantes': len(cnpj_para_nome_coluna_k_map),
                'responsaveis_rede': len(responsavel_rede_planilha)
            },
            'planilha_data': {
                'razoes_sociais_planilha': razoes_sociais_planilha,
                'cnpjs_planilha': cnpjs_planilha,
                'cnpj_para_nome_coluna_k_map': cnpj_para_nome_coluna_k_map,
                'responsavel_rede_planilha': responsavel_rede_planilha
            }
        })
        
    except Exception as e:
        return jsonify({'error': f'Erro ao processar planilha: {str(e)}'}), 500

@validador_bp.route('/processar-documentos', methods=['POST'])
@cross_origin()
def processar_documentos():
    try:
        data = request.get_json()
        document_urls = data.get('document_urls', [])
        planilha_data = data.get('planilha_data', {})
        
        if not document_urls:
            return jsonify({'error': 'URLs dos documentos são obrigatórias'}), 400
        
        if not planilha_data:
            return jsonify({'error': 'Dados da planilha são obrigatórios'}), 400
        
        resultados = []
        
        for url in document_urls[:3]:  
            resultado = processar_documento_individual(url, planilha_data)
            resultados.append(resultado)
        
        return jsonify({
            'success': True,
            'resultados': resultados
        })
        
    except Exception as e:
        return jsonify({'error': f'Erro ao processar documentos: {str(e)}'}), 500

def processar_documento_individual(document_url, planilha_data):
    resultado = {
        'url': document_url,
        'status': 'processando',
        'dados_extraidos': {},
        'validacoes': {},
        'dados_receita': {},
        'erro': None
    }
    
    try:
        razoes_sociais_planilha = planilha_data.get('razoes_sociais_planilha', [])
        cnpjs_planilha = planilha_data.get('cnpjs_planilha', [])
        cnpj_para_nome_coluna_k_map = planilha_data.get('cnpj_para_nome_coluna_k_map', {})
        responsavel_rede_planilha = planilha_data.get('responsavel_rede_planilha', [])
        
        raw_text_content, doc_type, error = get_document_content(document_url)
        
        if error:
            resultado['erro'] = error
            resultado['status'] = 'erro'
            return resultado
        
        cnpj_documento = extract_cnpj_from_document(document_url, raw_text_content)
        representante_legal_pdf = extract_legal_representative_from_eu(raw_text_content)
        specific_name_found = check_specific_names_presence_in_pdf(raw_text_content, responsavel_rede_planilha)
        data_documento = extract_and_normalize_date(raw_text_content)
        
        resultado['dados_extraidos'] = {
            'cnpj': cnpj_documento,
            'representante_legal': representante_legal_pdf,
            'nome_especifico_encontrado': specific_name_found,
            'data_documento': data_documento.strftime('%d/%m/%Y') if data_documento else None,
            'tipo_documento': doc_type
        }
        
        dados_receita = None
        if cnpj_documento:
            dados_receita = consultar_cnpj_receita_federal(cnpj_documento)
            
            if dados_receita:
                logradouro_receita = dados_receita.get('logradouro', 'Não informado') + \
                                   ", " + str(dados_receita.get('numero', 'S/N')) + \
                                   (" " + dados_receita.get('complemento', '') if dados_receita.get('complemento') else "") + \
                                   " - " + dados_receita.get('bairro', 'Não informado') + \
                                   ", " + dados_receita.get('municipio', 'Não informado') + \
                                   " - " + dados_receita.get('uf', 'NI') + \
                                   ", CEP: " + dados_receita.get('cep', 'Não informado')

                atividade_principal_receita_data = dados_receita.get('atividade_principal')
                if atividade_principal_receita_data and isinstance(atividade_principal_receita_data, list) and atividade_principal_receita_data:
                    cnae_codigo = atividade_principal_receita_data[0].get('code', 'Não informado')
                    cnae_descricao = atividade_principal_receita_data[0].get('text', 'Não informado')
                else:
                    cnae_codigo = "Não informado"
                    cnae_descricao = "Não informado"
                
                resultado['dados_receita'] = {
                    'razao_social': dados_receita.get('nome', 'Não informado'),
                    'situacao_cadastral': dados_receita.get('situacao', 'Não informado'),
                    'logradouro': logradouro_receita,
                    'cnae': cnae_codigo,
                    'atividade_principal': cnae_descricao
                }
        
        validacoes = {}
        
        razao_social_validada = False
        if dados_receita and razoes_sociais_planilha:
            razao_social_receita_normalizada = normalize_string(dados_receita.get('nome', ''))
            razoes_sociais_planilha_normalizadas = [normalize_string(rs) for rs in razoes_sociais_planilha]
            razao_social_validada = razao_social_receita_normalizada in razoes_sociais_planilha_normalizadas
        
        cnpj_validado_planilha = False
        if cnpj_documento and cnpjs_planilha:
            cnpjs_planilha_normalizados = [normalize_cnpj(c) for c in cnpjs_planilha]
            cnpj_validado_planilha = cnpj_documento in cnpjs_planilha_normalizados
        
        cnpj_validado_receita_ativo = False
        if dados_receita:
            situacao = dados_receita.get('situacao', '').lower()
            cnpj_validado_receita_ativo = 'ativa' in situacao or 'ativo' in situacao
        
        representante_validado = False
        if representante_legal_pdf and cnpj_documento and cnpj_para_nome_coluna_k_map:
            nome_esperado_planilha = cnpj_para_nome_coluna_k_map.get(cnpj_documento)
            if nome_esperado_planilha:
                representante_validado = normalize_string(representante_legal_pdf) == normalize_string(nome_esperado_planilha)
        
        nome_especifico_validado = specific_name_found is not None
        
        data_validada = False
        if data_documento:
            data_limite = datetime.now() - timedelta(days=30)
            data_validada = data_documento >= data_limite
        
        validacoes = {
            'razao_social_validada': razao_social_validada,
            'cnpj_validado_planilha': cnpj_validado_planilha,
            'cnpj_ativo_receita': cnpj_validado_receita_ativo,
            'representante_validado': representante_validado,
            'nome_especifico_validado': nome_especifico_validado,
            'data_validada': data_validada
        }
        
        resultado['validacoes'] = validacoes
        
        todas_validacoes = all(validacoes.values())
        resultado['status'] = 'valido' if todas_validacoes else 'invalido'
        
        return resultado
        
    except Exception as e:
        resultado['erro'] = str(e)
        resultado['status'] = 'erro'
        return resultado
