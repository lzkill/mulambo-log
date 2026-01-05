# Mulambo Log

Aplicação para calcular e registrar o Índice de Mulambo, sobrepondo um gráfico de desempenho em uma selfie.

## Índice de Mulambo

Fórmula: `1 - n/m`
Onde:
- `n`: dias de treino.
- `m`: dias de referência (365 para anual).

## Funcionalidades

- Registro de treino persisting timestamp UTC em SQLite.
- Captura de foto via câmera frontal (Web API).
- Geração de gráfico com índices: Atual, Max Potencial, Histórico.
- Composição de imagem (Foto + Gráfico).
- Compartilhamento via Web Share API.

## Como Rodar

### Com Docker Compose (Recomendado)

1. Construa e inicie os containers:
```bash
docker-compose up --build
```
2. Acesse `http://localhost:5000`.

### Localmente (com venv)

1. Crie e ative o ambiente virtual:
```bash
# Linux/macOS
python3 -m venv venv
source venv/bin/activate

# Windows
python -m venv venv
venv\Scripts\activate
```

2. Instale as dependências:
```bash
pip install -r requirements.txt
```

3. Inicie a aplicação:
```bash
flask run
```

4. Acesse `http://localhost:5000`.

## Variáveis de Ambiente

- `FLASK_APP`: Ponto de entrada da aplicação (`app.py`).
- `FLASK_ENV`: Ambiente (`development` ou `production`).

## Notas

- A aplicação requer HTTPS ou localhost para acessar a câmera (Web Privacy Check).
- O banco de dados SQLite é persistido no volume `./instance`.
