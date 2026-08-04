<div align="center">

# Orça Rápido Monolítico — Paredes em Painéis EPS

<p align="center">
  <b>Plataforma Inteligente para Medição de Paredes em Painéis Monolíticos (EPS) & Emissão Automática de Propostas Comerciais em PDF</b>
</p>

![Python](https://img.shields.io/badge/Python-3.11-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Streamlit](https://img.shields.io/badge/Streamlit-1.60.0-FF4B4B?style=for-the-badge&logo=streamlit&logoColor=white)
![LibreDWG](https://img.shields.io/badge/LibreDWG-0.14-00599C?style=for-the-badge&logo=gnu&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-Ready-2496ED?style=for-the-badge&logo=docker&logoColor=white)

</div>

---

## 📌 Visão Geral

O **Orça Rápido Monolítico** é um sistema genérico e customizável para construtoras, empreiteiras e orçadores que trabalham com o sistema construtivo de **painéis monolíticos (EPS)**. O sistema lê plantas baixas vetoriais em formatos **DWG** ou **DXF**, calcula a metragem linear de parede por pavimento e gera propostas comerciais profissionais em PDF com o cálculo:

$$\text{Valor Total (R\$)} = \text{Metragem Confirmada (m)} \times \text{Valor por Metro (R\$/m)}$$

---

## ⚡ Funcionalidades Principais

1. **White Label & Customizável**: Campos abertos para cadastro da empresa contratada (remetente) e do cliente contratante. Sem marcas ou logos fixas no sistema.
2. **Autopreenchimento por CNPJ**: Integração com consulta da Receita Federal. Ao digitar o CNPJ da empresa ou do cliente, o sistema preenche automaticamente Razão Social, Nome Fantasia, Endereço, Telefone e E-mail.
3. **Conversão Nativa DWG → DXF**: Suporte transparente a arquivos `.dwg` utilizando a biblioteca open-source **LibreDWG 0.14**.
4. **Extração Geométrica Inteligente**: Algoritmo que identifica traçados de parede por camadas (layers) e classifica entre alta confiança e linhas a revisar.
5. **Emissão de Propostas em PDF**: Geração de orçamentos estilizados prontos para download e assinatura.

---

## 🚀 Como Executar o Projeto

### 1. Rodando com Docker (Recomendado)

```bash
# 1. Construir a imagem Docker
docker build -t orca-rapido-monolitico .

# 2. Executar o container na porta 8501
docker run -p 8501:8501 orca-rapido-monolitico
```

Acesse no navegador: [`http://localhost:8501`](http://localhost:8501)

---

### 2. Rodando Localmente

```bash
# Instalar dependências
pip install -r requirements.txt

# Executar aplicação Streamlit
streamlit run app.py
```

---

<div align="center">
  <b>Orça Rápido Monolítico — Tecnologia & Automação para o Sistema Construtivo de Painéis EPS</b>
</div>