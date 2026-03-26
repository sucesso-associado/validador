class ValidadorDocumentos {
    constructor() {
        this.planilhaData = null;
        this.resultados = [];
        this.init();
    }

    init() {
        this.bindEvents();
        // Dispara o carregamento automático da planilha ao iniciar a página
        this.carregarPlanilha();
    }

    bindEvents() {
        // Iniciar validação
        document.getElementById('iniciar-validacao').addEventListener('click', () => {
            this.iniciarValidacao();
        });

        // Download relatório
        document.getElementById('download-relatorio').addEventListener('click', () => {
            this.downloadRelatorio();
        });

        // Monitorar mudanças nas URLs
        document.getElementById('document-urls').addEventListener('input', () => {
            this.updateUI();
        });
    }

    updateUI() {
        const documentUrls = document.getElementById('document-urls').value.trim();
        const iniciarBtn = document.getElementById('iniciar-validacao');

        // Habilitar botão de validação apenas se planilha carregada e URLs fornecidas
        if(iniciarBtn) {
            iniciarBtn.disabled = !this.planilhaData || !documentUrls;
        }
    }

    async carregarPlanilha() {
        const statusElement = document.getElementById('status-planilha');
        
        // Mostrar status de loading automático
        this.showAlert(statusElement, 'info', '<i class="fas fa-spinner fa-spin me-1"></i> Sincronizando com a base de dados (Google Sheets)...');

        try {
            const response = await fetch('/api/carregar-planilha', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({}) // Backend agora tem a URL fixa
            });

            const data = await response.json();

            if (data.success) {
                this.planilhaData = data.planilha_data;
                const { dados } = data;
                
                this.showAlert(statusElement, 'success', 
                    `✅ Base de dados sincronizada com sucesso!<br>
                     📊 ${dados.razoes_sociais} razões sociais | 🏢 ${dados.cnpjs} CNPJs | 👤 ${dados.representantes} representantes`
                );
                
                this.updateUI();
            } else {
                throw new Error(data.error || 'Erro desconhecido');
            }

        } catch (error) {
            console.error('Erro ao carregar planilha:', error);
            this.showAlert(statusElement, 'danger', `❌ Erro ao conectar com base de dados: ${error.message}`);
            this.planilhaData = null;
        } finally {
            this.updateUI();
        }
    }

    async iniciarValidacao() {
        const documentUrls = this.parseDocumentUrls();
        
        if (documentUrls.length === 0) {
            alert('Por favor, insira pelo menos uma URL de documento');
            return;
        }

        if (documentUrls.length > 3) {
            alert('Máximo de 3 documentos permitidos simultaneamente devido ao limite da Receita Federal.');
            return;
        }

        // Mostrar seção de progresso
        document.getElementById('secao-progresso').style.display = 'block';
        document.getElementById('secao-resultados').style.display = 'none';
        
        // Resetar progresso
        this.updateProgress(0, 'Iniciando validação...');
        
        // Desabilitar botão
        const iniciarBtn = document.getElementById('iniciar-validacao');
        iniciarBtn.disabled = true;
        iniciarBtn.innerHTML = '<i class="fas fa-spinner fa-spin me-2"></i>Processando...';

        try {
            this.updateProgress(20, 'Enviando documentos para processamento...');

            const response = await fetch('/api/processar-documentos', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    document_urls: documentUrls,
                    planilha_data: this.planilhaData
                })
            });

            this.updateProgress(60, 'Processando documentos e consultando Receita Federal...');

            const data = await response.json();

            if (data.success) {
                this.updateProgress(100, 'Processamento concluído!');
                this.resultados = data.resultados;
                this.exibirResultados();
            } else {
                throw new Error(data.error || 'Erro no processamento');
            }

        } catch (error) {
            console.error('Erro no processamento:', error);
            this.updateProgress(0, `❌ Erro: ${error.message}`);
            this.addLog(`❌ Erro: ${error.message}`, 'danger');
        } finally {
            iniciarBtn.disabled = false;
            iniciarBtn.innerHTML = '<i class="fas fa-play me-2"></i>Iniciar Validação';
            this.updateUI();
        }
    }

    parseDocumentUrls() {
        const text = document.getElementById('document-urls').value.trim();
        if (!text) return [];

        return text.split(/[,\n]/)
            .map(url => url.trim())
            .filter(url => url.length > 0);
    }

    updateProgress(percentage, message) {
        const progressBar = document.getElementById('progress-bar');
        progressBar.style.width = `${percentage}%`;
        progressBar.setAttribute('aria-valuenow', percentage);
        
        this.addLog(message, percentage === 100 ? 'success' : 'info');
    }

    addLog(message, type = 'info') {
        const logContainer = document.getElementById('log-processamento');
        const timestamp = new Date().toLocaleTimeString();
        
        const logEntry = document.createElement('div');
        logEntry.className = `text-${type === 'danger' ? 'danger' : type === 'success' ? 'success' : 'light'}`;
        logEntry.innerHTML = `[${timestamp}] ${message}`;
        
        logContainer.appendChild(logEntry);
        logContainer.scrollTop = logContainer.scrollHeight;
    }

    exibirResultados() {
        const container = document.getElementById('resultados-container');
        container.innerHTML = '';

        document.getElementById('secao-resultados').style.display = 'block';

        const validos = this.resultados.filter(r => r.status === 'valido').length;
        const invalidos = this.resultados.filter(r => r.status === 'invalido').length;
        const erros = this.resultados.filter(r => r.status === 'erro').length;

        const statsHtml = `
            <div class="row mb-4">
                <div class="col-md-4">
                    <div class="card text-center resultado-card valido">
                        <div class="card-body">
                            <h3 class="text-success">${validos}</h3>
                            <p class="mb-0">Documentos Válidos</p>
                        </div>
                    </div>
                </div>
                <div class="col-md-4">
                    <div class="card text-center resultado-card invalido">
                        <div class="card-body">
                            <h3 class="text-danger">${invalidos}</h3>
                            <p class="mb-0">Documentos Inválidos</p>
                        </div>
                    </div>
                </div>
                <div class="col-md-4">
                    <div class="card text-center resultado-card erro">
                        <div class="card-body">
                            <h3 class="text-warning">${erros}</h3>
                            <p class="mb-0">Erros de Processamento</p>
                        </div>
                    </div>
                </div>
            </div>
        `;

        container.innerHTML = statsHtml;

        this.resultados.forEach((resultado, index) => {
            const cardHtml = this.criarCardResultado(resultado, index + 1);
            container.innerHTML += cardHtml;
        });
    }

    criarCardResultado(resultado, numero) {
        const statusClass = resultado.status === 'valido' ? 'valido' : 
                           resultado.status === 'invalido' ? 'invalido' : 'erro';
        
        const statusIcon = resultado.status === 'valido' ? 'fa-check-circle text-success' :
                          resultado.status === 'invalido' ? 'fa-times-circle text-danger' : 
                          'fa-exclamation-triangle text-warning';

        const statusText = resultado.status === 'valido' ? 'Válido' :
                          resultado.status === 'invalido' ? 'Inválido' : 'Erro';

        let conteudo = '';

        if (resultado.erro) {
            conteudo = `
                <div class="alert alert-danger">
                    <i class="fas fa-exclamation-triangle me-2"></i>
                    <strong>Erro:</strong> ${resultado.erro}
                </div>
            `;
        } else {
            const dados = resultado.dados_extraidos || {};
            const receita = resultado.dados_receita || {};
            const validacoes = resultado.validacoes || {};

            conteudo = `
                <div class="row">
                    <div class="col-md-6">
                        <h6><i class="fas fa-file-alt me-2"></i>Dados Extraídos</h6>
                        <table class="table table-sm table-dados">
                            <tr><td><strong>CNPJ:</strong></td><td>${dados.cnpj || 'Não encontrado'}</td></tr>
                            <tr><td><strong>Representante Legal:</strong></td><td>${dados.representante_legal || 'Não encontrado'}</td></tr>
                            <tr><td><strong>Data:</strong></td><td>${dados.data_documento || 'Não encontrada'}</td></tr>
                            <tr><td><strong>Nome Específico:</strong></td><td>${dados.nome_especifico_encontrado || 'Não encontrado'}</td></tr>
                        </table>
                    </div>
                    <div class="col-md-6">
                        <h6><i class="fas fa-building me-2"></i>Dados da Receita Federal</h6>
                        <table class="table table-sm table-dados">
                            <tr><td><strong>Razão Social:</strong></td><td>${receita.razao_social || 'Não consultado'}</td></tr>
                            <tr><td><strong>Situação:</strong></td><td>${receita.situacao_cadastral || 'Não consultado'}</td></tr>
                            <tr><td><strong>CNAE:</strong></td><td>${receita.cnae || 'Não consultado'}</td></tr>
                            <tr><td><strong>Atividade:</strong></td><td>${receita.atividade_principal || 'Não consultado'}</td></tr>
                            <tr><td><strong>Endereço:</strong></td><td>${receita.logradouro || 'Não consultado'}</td></tr>
                        </table>
                    </div>
                </div>
                
                <hr>
                
                <h6><i class="fas fa-check-double me-2"></i>Validações</h6>
                <div class="row">
                    <div class="col-md-6">
                        ${this.criarItemValidacao('CNPJ na Planilha', validacoes.cnpj_validado_planilha)}
                        ${this.criarItemValidacao('Razão Social Válida', validacoes.razao_social_validada)}
                        ${this.criarItemValidacao('CNPJ Ativo na Receita', validacoes.cnpj_ativo_receita)}
                    </div>
                    <div class="col-md-6">
                        ${this.criarItemValidacao('Representante Válido', validacoes.representante_validado)}
                        ${this.criarItemValidacao('Nome Específico Válido', validacoes.nome_especifico_validado)}
                        ${this.criarItemValidacao('Data Válida (30 dias)', validacoes.data_validada)}
                    </div>
                </div>
            `;
        }

        return `
            <div class="card mb-3 resultado-card ${statusClass} fade-in-up">
                <div class="card-header d-flex justify-content-between align-items-center">
                    <h5 class="mb-0">
                        <i class="fas ${statusIcon} me-2"></i>
                        Documento ${numero}
                    </h5>
                    <span class="badge badge-status badge-${statusClass}">${statusText}</span>
                </div>
                <div class="card-body">
                    <p class="text-muted mb-3">
                        <i class="fas fa-link me-1"></i>
                        <small>${resultado.url}</small>
                    </p>
                    ${conteudo}
                </div>
            </div>
        `;
    }

    criarItemValidacao(label, status) {
        const icon = status ? 'fa-check text-success' : 'fa-times text-danger';
        const text = status ? 'Válido' : 'Inválido';
        
        return `
            <div class="d-flex align-items-center mb-2">
                <i class="fas ${icon} me-2"></i>
                <span>${label}: <strong>${text}</strong></span>
            </div>
        `;
    }

    downloadRelatorio() {
        if (!this.resultados || this.resultados.length === 0) {
            alert('Nenhum resultado para download');
            return;
        }

        const relatorio = {
            timestamp: new Date().toISOString(),
            total_documentos: this.resultados.length,
            validos: this.resultados.filter(r => r.status === 'valido').length,
            invalidos: this.resultados.filter(r => r.status === 'invalido').length,
            erros: this.resultados.filter(r => r.status === 'erro').length,
            resultados: this.resultados
        };

        const blob = new Blob([JSON.stringify(relatorio, null, 2)], { 
            type: 'application/json' 
        });
        
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `relatorio-validacao-${new Date().toISOString().split('T')[0]}.json`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    }

    showAlert(element, type, message) {
        element.className = `alert alert-${type} mt-2`;
        element.innerHTML = `<i class="fas fa-${type === 'success' ? 'check' : type === 'danger' ? 'times' : 'info'}-circle me-1"></i>${message}`;
    }
}

document.addEventListener('DOMContentLoaded', () => {
    new ValidadorDocumentos();
});
