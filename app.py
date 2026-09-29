from flask import Flask, render_template
import os

app = Flask(__name__)


@app.route('/')
def home():
    equipa = [
        {
            'nome': 'Pedro Cristóvão',
            'cargo': 'Fundador & Master Barber',
            'foto': '/static/pedro.jpg.png',
            'especialidade': 'Cortes Clássicos & Visagismo'
        },
        {
            'nome': 'Oliveira',
            'cargo': 'Barber Specialist',
            'foto': '/static/oliveira.jpg.png',
            'especialidade': 'Barboterapia & Fade de Precisão'
        }
    ]
    servicos = [
        {'categoria': 'Cortes', 'nome': 'Corte Clássico / Fade', 'preco': '12€', 'tempo': '30 min'},
        {'categoria': 'Cortes', 'nome': 'Corte de Máquina', 'preco': '10€', 'tempo': '20 min'},
        {'categoria': 'Cortes', 'nome': 'Corte & Sobrancelha', 'preco': '14€', 'tempo': '40 min'},
        {'categoria': 'Barba', 'nome': 'Barba Tradicional', 'preco': '8€', 'tempo': '20 min'},
        {'categoria': 'Barba', 'nome': 'Barboterapia Premium', 'preco': '12€', 'tempo': '30 min'},
        {'categoria': 'Combos', 'nome': 'Combo PointFino (Corte + Barba + Sobrancelha)', 'preco': '20€', 'tempo': '50 min'},
        {'categoria': 'Cuidados', 'nome': 'Pigmentação & Platinado', 'preco': 'Sob Consulta', 'tempo': '60 min'},
    ]
    return render_template('index.html', equipa=equipa, servicos=servicos)


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
