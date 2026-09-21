from flask import Flask, render_template, request
import resend

app = Flask(__name__)

# Configuração de envio de confirmações de reserva/contacto via Resend
resend.api_key = "re_hhxHoD9L_7U4KWye4zcQGteb9QytPombM"
EMAIL_DESTINO = "marcocaldeira1987@gmail.com"

@app.route('/', methods=['GET', 'POST'])
def home():
    mensagem_sucesso = None
    
    if request.method == 'POST':
        nome = request.form.get('nome')
        telemovel = request.form.get('telemovel')
        servico = request.form.get('servico')
        barbeiro = request.form.get('barbeiro')
        data_hora = request.form.get('data_hora')
        
        try:
            resend.Emails.send({
                "from": "PointFino Barbershop <onboarding@resend.dev>",
                "to": [EMAIL_DESTINO],
                "subject": f"💈 Nova Reserva PointFino: {nome} - {servico}",
                "html": f"""
                <h2>Nova Reserva Recebida!</h2>
                <p><strong>Cliente:</strong> {nome}</p>
                <p><strong>Telemóvel:</strong> {telemovel}</p>
                <p><strong>Serviço:</strong> {servico}</p>
                <p><strong>Barbeiro Preferido:</strong> {barbeiro}</p>
                <p><strong>Data/Hora Solicitada:</strong> {data_hora}</p>
                """
            })
            mensagem_sucesso = f"Obrigado, {nome}! A tua reserva para {servico} foi enviada. Confirmamos em breve!"
        except Exception as e:
            print(f"Erro ao enviar reserva: {e}")
            mensagem_sucesso = f"Obrigado, {nome}! Recebemos a tua solicitação de agendamento."

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

    return render_template('index.html', equipa=equipa, servicos=servicos, mensagem_sucesso=mensagem_sucesso)


import os

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)