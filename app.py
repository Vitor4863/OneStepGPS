import math
import requests
from flask import Flask, render_template, request, jsonify, redirect, url_for, session

app = Flask(__name__)
app.secret_key = "devverse_secret"

# Configurações OneStepGPS
API_KEY = "cWpVu8yTfVRytZRt95Tnkv_VmBfUywfg_oT-GkqGzlI"
URL_API = "https://track.onestepgps.com/v3/api/public/marker"

USER = {"username": "admin", "password": "1234"}

# Funções Utilitárias
def calcular_distancia(lat1, lon1, lat2, lon2):
    try:
        R = 6371 # Raio da Terra em km
        phi1, phi2 = math.radians(float(lat1)), math.radians(float(lat2))
        dlat = math.radians(float(lat2)-float(lat1))
        dlon = math.radians(float(lon2)-float(lon1))
        
        a = math.sin(dlat/2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlon/2)**2
        return R * (2 * math.atan2(math.sqrt(a), math.sqrt(1-a)))
    except: 
        return float('inf')

@app.route('/')
def index():
    if not session.get("logged"): return redirect(url_for("login"))
    if 'clientes' not in session: session['clientes'] = []
    return render_template('index.html', clientes=session['clientes'])

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        if request.form.get('username') == USER['username'] and request.form.get('password') == USER['password']:
            session['logged'] = True
            return redirect(url_for('index'))
        return render_template('login.html', error="Login inválido")
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/limpar')
def limpar():
    session['clientes'] = []
    session.modified = True
    return redirect(url_for('index'))

@app.route('/cadastrar_cep', methods=['POST'])
def cadastrar_cep():
    if not session.get("logged"): return jsonify({"success": False, "error": "Não autorizado"})

    nome = request.form.get('nome')
    cep_input = request.form.get('cep', '').strip().replace("-", "")
    numero = request.form.get('numero', '').strip()

    try:
        full_address = ""
        
        # 1. LÓGICA HÍBRIDA: BRASIL (CEP) OU EUA (ZIP CODE)
        if len(cep_input) == 8 and cep_input.isdigit():
            # Tenta ViaCEP para endereços brasileiros
            viacep_res = requests.get(f"https://viacep.com.br/ws/{cep_input}/json/").json()
            if "erro" not in viacep_res:
                rua = viacep_res.get('logradouro', '')
                bairro = viacep_res.get('bairro', '')
                cidade = viacep_res.get('localidade', '')
                full_address = f"{rua}, {numero}, {bairro}, {cidade}, Brazil"
            else:
                full_address = f"{cep_input}, {numero}, Brazil"
        else:
            # Caso contrário, assume ZIP Code (EUA) ou padrão internacional
            # Nos EUA, o número costuma vir antes do código postal na busca
            full_address = f"{numero} {cep_input}, USA"

        # 2. GEOCODIFICAÇÃO (NOMINATIM) - Obtém as coordenadas reais para a API
        geo_res = requests.get(
            f"https://nominatim.openstreetmap.org/search?q={full_address}&format=json&limit=1", 
            headers={'User-Agent': 'DevVerse_Logistics_App'}
        ).json()
        
        if not geo_res: 
            return jsonify({"success": False, "error": "Endereço não localizado no mapa global."})
        
        lat_cli = float(geo_res[0]['lat'])
        lng_cli = float(geo_res[0]['lon'])
        display_address = geo_res[0]['display_name']

        # 3. BUSCA MOTORISTA MAIS PRÓXIMO (OneStepGPS)
        headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
        res_v = requests.get("https://track.onestepgps.com/v3/api/public/device-info?lat_lng=1", headers=headers).json()
        
        melhor_v, menor_d, motorista_coords = "Indisponível", float('inf'), None
        lista = res_v if isinstance(res_v, list) else [res_v]
        
        for v in lista:
            v_lat = v.get('lat') or v.get('last_tap', {}).get('lat')
            v_lng = v.get('lng') or v.get('last_tap', {}).get('lng')
            if v_lat and v_lng:
                d = calcular_distancia(lat_cli, lng_cli, v_lat, v_lng)
                if d < menor_d:
                    menor_d, melhor_v = d, v.get('display_name', 'Rastreador')
                    motorista_coords = {"lat": float(v_lat), "lng": float(v_lng)}

        # 4. CADASTRO NA API ONESTEPGPS (Mantendo o seu payload original)
        payload = {
            "display_name": nome, 
            "active": True, 
            "status": "active", 
            "marker_type": "point",
            "detail": {
                "description": display_address, 
                "lat_lng": {"lat": lat_cli, "lng": lng_cli}
            }
        }
        requests.post(URL_API, json=payload, headers=headers)

        # 5. ATUALIZAR SESSÃO
        distancia_arredondada = round(menor_d, 2) if menor_d != float('inf') else 0
        temp_list = list(session.get('clientes', []))
        temp_list.append({
            "nome": nome, 
            "endereco": display_address, 
            "motorista": melhor_v, 
            "distancia": distancia_arredondada
        })
        session['clientes'] = temp_list
        session.modified = True

        return jsonify({
            "success": True,
            "motorista": melhor_v,
            "distancia": distancia_arredondada,
            "cliente_coords": {"lat": lat_cli, "lng": lng_cli},
            "motorista_coords": motorista_coords
        })

    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

if __name__ == '__main__':
    app.run(debug=True)