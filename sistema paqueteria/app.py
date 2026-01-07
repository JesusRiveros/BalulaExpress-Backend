from flask import Flask, render_template, request, session, redirect, url_for
from datetime import datetime, timedelta
import requests
import os
from fpdf import FPDF
import io
from flask import send_file
import uuid

app = Flask(__name__)
app.secret_key = 'una_clave_super_secreta_1234'

DISTANCIA_TARIFAS = [
    (50, 60),
    (500, 120),
    (1500, 250),
    (3000, 350),
    (float('inf'), 400)
]

COSTO_POR_KG_EXTRA = 10
COSTO_ENVIO_EXPRES = 20
COSTO_CO2 = 5
BOX_COSTS = {
    'small': 10,
    'books': 15,
    'shoes': 25,
    'move': 40
}

GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")

def descomponer_direccion(direccion):
    try:
        url = 'https://maps.googleapis.com/maps/api/geocode/json'
        params = {'address': direccion, 'key': GOOGLE_MAPS_API_KEY}
        resp = requests.get(url, params=params).json()
        components = resp['results'][0]['address_components']

        resultado = {
            'street': '',
            'neighborhood': '',
            'city': '',
            'state': ''
        }
        for comp in components:
            tipos = comp['types']
            if 'street_number' in tipos:
                resultado['street'] = comp['long_name'] + ' ' + resultado['street']
            if 'route' in tipos:
                resultado['street'] += comp['long_name']
            if 'sublocality_level_1' in tipos or 'neighborhood' in tipos:
                resultado['neighborhood'] = comp['long_name']
            if 'locality' in tipos:
                resultado['city'] = comp['long_name']
            if 'administrative_area_level_1' in tipos:
                resultado['state'] = comp['long_name']
        resultado['street'] = resultado['street'].strip()
        return resultado
    except Exception as e:
        print("Error descomponiendo dirección:", e)
        return {
            'street': direccion,
            'neighborhood': '',
            'city': '',
            'state': ''
        }

@app.route('/')
def index():
    return render_template('index.html', paso_actual=1)

@app.route('/calculate', methods=['POST'])
def calculate():
    origin = request.form.get('origin')
    destination = request.form.get('destination')
    tipo_entrega = request.form.get('tipo_entrega')
    email = request.form.get('email')
    weight = float(request.form.get('weight'))
    length = float(request.form.get('length'))
    width = float(request.form.get('width'))
    height = float(request.form.get('height'))
    lat = request.form.get('lat')
    lon = request.form.get('lon')
    eco_packaging = request.form.get('eco_packaging')
    shipping_type = request.form.get('shipping_type')
    compensate = request.form.get('compensate') == 'yes'
    box_choice = request.form.get('box_choice')

    sender_parts = descomponer_direccion(origin)
    receiver_parts = descomponer_direccion(destination)

    session['sender_street'] = sender_parts['street']
    session['sender_neighborhood'] = sender_parts['neighborhood']
    session['sender_city'] = sender_parts['city']
    session['sender_state'] = sender_parts['state']

    session['receiver_street'] = receiver_parts['street']
    session['receiver_neighborhood'] = receiver_parts['neighborhood']
    session['receiver_city'] = receiver_parts['city']
    session['receiver_state'] = receiver_parts['state']

    distance_km = 100
    try:
        response = requests.get(
            'https://maps.googleapis.com/maps/api/distancematrix/json',
            params={'origins': origin, 'destinations': destination, 'key': GOOGLE_MAPS_API_KEY}
        )
        data = response.json()
        distance_meters = data['rows'][0]['elements'][0]['distance']['value']
        distance_km = round(distance_meters / 1000, 2)
    except Exception as e:
        print("Error al obtener distancia:", e)

    costo_base = next(precio for rango, precio in DISTANCIA_TARIFAS if distance_km <= rango)
    peso_extra = max(0, weight - 1)
    costo_peso = peso_extra * COSTO_POR_KG_EXTRA
    costo_caja = BOX_COSTS.get(box_choice, 0)

    costo_extra = 0
    if shipping_type == 'fast':
        costo_extra += COSTO_ENVIO_EXPRES
    if compensate:
        costo_extra += COSTO_CO2

    cost = round(costo_base + costo_peso + costo_caja + costo_extra, 2)
    dias_estimados = 1 if shipping_type == 'fast' else 3
    delivery_date = (datetime.now() + timedelta(days=dias_estimados)).strftime('%Y-%m-%d')
    co2_emission = round(weight * distance_km * 0.21 / 1000, 2)

    session['costo_estimado'] = cost
    session['fecha_entrega_estimada'] = delivery_date

    return render_template(
        'result.html',
        origin=origin,
        tipo_entrega=tipo_entrega,
        destination=destination,
        email=email,
        cost=cost,
        delivery_date=delivery_date,
        lat=lat,
        lon=lon,
        eco_packaging=eco_packaging,
        shipping_type=shipping_type,
        co2_emission=co2_emission,
        distance_km=distance_km,
        compensated=compensate,
        box_choice=box_choice,
        weight=weight,
        length=length,
        width=width,
        height=height,
        paso_actual=2
    )

@app.route('/completar', methods=['GET', 'POST'])
def completar():
    if request.method == 'POST':
        session['sender_name'] = request.form.get('sender_name', '')
        session['sender_phone'] = request.form.get('sender_phone', '')
        session['sender_street'] = request.form.get('sender_street', '')
        session['sender_neighborhood'] = request.form.get('sender_neighborhood', '')
        session['sender_city'] = request.form.get('sender_city', '')
        session['sender_state'] = request.form.get('sender_state', '')

        session['receiver_name'] = request.form.get('receiver_name', '')
        session['receiver_phone'] = request.form.get('receiver_phone', '')
        session['receiver_street'] = request.form.get('receiver_street', '')
        session['receiver_neighborhood'] = request.form.get('receiver_neighborhood', '')
        session['receiver_city'] = request.form.get('receiver_city', '')
        session['receiver_state'] = request.form.get('receiver_state', '')
        session['receiver_references'] = request.form.get('receiver_references', '')

        session['costo_estimado'] = request.form.get('costo_estimado', session.get('costo_estimado', 'No definido'))
        session['fecha_entrega_estimada'] = request.form.get('fecha_entrega_estimada', session.get('fecha_entrega_estimada', 'No definida'))

        return redirect(url_for('pago'))

    return render_template(
        'completar.html',
        paso_actual=3,
        sender_street=session.get('sender_street', ''),
        sender_neighborhood=session.get('sender_neighborhood', ''),
        sender_city=session.get('sender_city', ''),
        sender_state=session.get('sender_state', ''),
        receiver_street=session.get('receiver_street', ''),
        receiver_neighborhood=session.get('receiver_neighborhood', ''),
        receiver_city=session.get('receiver_city', ''),
        receiver_state=session.get('receiver_state', '')
    )

@app.route('/pago')
def pago():
    resumen = {
        'sender_name': session.get('sender_name', ''),
        'sender_phone': session.get('sender_phone', ''),
        'sender_street': session.get('sender_street', ''),
        'sender_neighborhood': session.get('sender_neighborhood', ''),
        'sender_city': session.get('sender_city', ''),
        'sender_state': session.get('sender_state', ''),
        'receiver_name': session.get('receiver_name', ''),
        'receiver_phone': session.get('receiver_phone', ''),
        'receiver_street': session.get('receiver_street', ''),
        'receiver_neighborhood': session.get('receiver_neighborhood', ''),
        'receiver_city': session.get('receiver_city', ''),
        'receiver_state': session.get('receiver_state', ''),
        'receiver_references': session.get('receiver_references', ''),
        'cost': session.get('costo_estimado', 'No definido'),
        'delivery_date': session.get('fecha_entrega_estimada', 'No definida')
    }
    return render_template('pago.html', resumen=resumen, paso_actual=4)

@app.route('/procesar_pago', methods=['POST'])
def procesar_pago():
    return redirect(url_for('fake_checkout'))

@app.route('/fake_checkout', methods=['GET', 'POST'])
def fake_checkout():
    resumen = {
        'cost': session.get('costo_estimado', 'No definido'),
        'sender_name': session.get('sender_name', ''),
        'receiver_name': session.get('receiver_name', '')
    }

    if request.method == 'POST':
        resultado = request.form.get('resultado')
        if resultado == 'success':
            return redirect(url_for('pago_exitoso'))
        elif resultado == 'failure':
            return redirect(url_for('pago_fallido'))
        else:
            return redirect(url_for('pago_pendiente'))

    return render_template('fake_checkout.html', resumen=resumen)

@app.route('/pago_exitoso')
def pago_exitoso():
    tracking_code = f"BLL-{str(uuid.uuid4())[:8].upper()}"
    session['tracking'] = tracking_code

    data = {
        'nombre_rem': session.get('sender_name', ''),
        'origen': f"{session.get('sender_street', '')}, {session.get('sender_city', '')}, {session.get('sender_state', '')}",
        'nombre_dest': session.get('receiver_name', ''),
        'destino': f"{session.get('receiver_street', '')}, {session.get('receiver_city', '')}, {session.get('receiver_state', '')}",
        'peso': session.get('weight', 'N/A'),  # agrega peso
        'costo': session.get('costo_estimado', 'N/A'),  # agrega costo
        'fecha_entrega': session.get('fecha_entrega_estimada', 'N/A')  # agrega fecha entrega
    }

    generar_guia_pdf(data, tracking_code)

    return render_template('pago_exitoso.html',
                           sender_name=data['nombre_rem'],
                           receiver_name=data['nombre_dest'],
                           tracking=tracking_code)

@app.route('/pago_fallido')
def pago_fallido():
    return render_template('pago_fallido.html')

@app.route('/pago_pendiente')
def pago_pendiente():
    return render_template('pago_pendiente.html')

class PDFDHLStyle(FPDF):
    def header(self):
        try:
            self.image('static/Balula logo.png', 10, 8, 40)  # Cambia a tu logo DHL o quita si no tienes
        except:
            pass
        self.set_draw_color(204, 0, 0)  # rojo DHL
        self.set_line_width(5)
        self.line(10, 35, 200, 35)
        self.ln(30)

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.set_text_color(128)
        fecha = datetime.now().strftime('%d/%m/%Y %H:%M')
        self.cell(0, 10, f'Guía generada el {fecha} - Página {self.page_no()}', align='C')

class PDFDHLStyle(FPDF):
    def header(self):
        # Logo DHL arriba izquierda
        try:
            self.image('static/dhl_logo.png', 10, 8, 50)  # Ajusta tamaño a 50 ancho
        except:
            pass
        self.set_draw_color(204, 0, 0)  # Rojo DHL
        self.set_line_width(3)
        self.line(10, 38, 200, 38)  # Línea roja debajo del logo
        self.ln(30)

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.set_text_color(128)
        fecha = datetime.now().strftime('%d/%m/%Y %H:%M')
        self.cell(0, 10, f'Guía generada el {fecha} - Página {self.page_no()}', align='C')

def generar_guia_pdf(data, tracking_code):
    pdf = PDFDHLStyle()
    pdf.add_page()

    # Título grande rojo
    pdf.set_font("Arial", 'B', 22)
    pdf.set_text_color(204, 0, 0)
    pdf.cell(0, 15, "GUÍA DE EMBARQUE", ln=True, align='C')
    pdf.ln(5)

    # Código de rastreo en caja amarilla grande
    pdf.set_fill_color(255, 204, 0)  # Amarillo DHL
    pdf.set_text_color(0)
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(0, 20, f"CÓDIGO DE RASTREO: {tracking_code}", border=1, ln=True, align='C', fill=True)
    pdf.ln(10)

    # Sección remitente y destinatario
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(95, 12, "REMITENTE", border=1, align='C')
    pdf.cell(0, 12, "DESTINATARIO", border=1, align='C', ln=True)

    pdf.set_font("Arial", '', 12)
    pdf.multi_cell(95, 10, f"{data.get('nombre_rem', '')}\n{data.get('origen', '')}", border=1)
    x_current = pdf.get_x()
    y_current = pdf.get_y() - 20
    pdf.set_xy(x_current + 95, y_current)
    pdf.multi_cell(0, 10, f"{data.get('nombre_dest', '')}\n{data.get('destino', '')}", border=1)
    pdf.ln(10)

    # Datos adicionales
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(50, 10, "Peso (kg)", border=1, align='C')
    pdf.cell(70, 10, "Costo Estimado", border=1, align='C')
    pdf.cell(0, 10, "Fecha Estimada de Entrega", border=1, align='C', ln=True)

    pdf.set_font("Arial", '', 12)
    pdf.cell(50, 12, str(data.get('peso', 'N/A')), border=1, align='C')
    pdf.cell(70, 12, f"${data.get('costo', 'N/A')}", border=1, align='C')
    pdf.cell(0, 12, data.get('fecha_entrega', 'N/A'), border=1, align='C', ln=True)
    pdf.ln(15)

    # Instrucciones o mensaje
    pdf.set_font("Arial", 'I', 10)
    pdf.multi_cell(0, 10,
                   "Por favor conserve esta guía de embarque para seguimiento y consultas.\n"
                   "Para mayor información, contacte nuestro centro de atención al cliente.\n"
                   "Gracias por confiar en nuestros servicios.")

    # Salida PDF en memoria
    pdf_bytes = pdf.output(dest='S').encode('latin-1')
    session['pdf_buf'] = pdf_bytes
    return pdf_bytes

@app.route('/download/guia')
def download_guia():
    pdf_bytes = session.get('pdf_buf')
    tracking = session.get('tracking')

    if not pdf_bytes or not tracking:
        return "No hay guía generada", 404

    return send_file(io.BytesIO(pdf_bytes),
                     download_name=f"guia_{tracking}.pdf",
                     as_attachment=True)


if __name__ == '__main__':
    app.run()
