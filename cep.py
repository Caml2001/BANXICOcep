from datetime import date, datetime
import os
from cep import Transferencia
import pdfplumber
from io import BytesIO
import json
import csv
import re  # Importamos el módulo 're' para expresiones regulares
from time import sleep  # Agregar esta importación al inicio


# Leer inputs desde archivo CSV
import csv
input_data_list = []
with open('consulta_CEP_pruebas.txt', 'r', encoding='utf-8') as f:
    csv_reader = csv.DictReader(f)
    input_data_list = list(csv_reader)

# Procesar cada línea del CSV
for index, input_data in enumerate(input_data_list, 1):
    try:
        # Agregar un delay entre consultas
        if index > 1:  # No esperar antes de la primera consulta
            sleep(5)  # Esperar 2 segundos entre consultas
        
        print(f"\nProcesando consulta {index} de {len(input_data_list)}")
        
        # Crear objeto Transferencia y validar
        fecha_parts = [int(part) for part in input_data['fecha'].split('-')]
        tr = Transferencia.validar(
            fecha=date(*fecha_parts),
            clave_rastreo=input_data['clave_rastreo'],
            emisor=input_data['emisor'],
            receptor=input_data['receptor'],
            cuenta=input_data['cuenta'],
            monto=float(input_data['monto']),
        )
        
        # Si tr es None, guardar en archivos noCEP
        if tr is None:
            print(f"No se encontró información para la clave de rastreo: {input_data['clave_rastreo']}")
            
            # Preparar datos para registro no encontrado
            no_cep_data = {
                'fecha_input': input_data['fecha'],
                'clave_rastreo_input': input_data['clave_rastreo'],
                'emisor_input': input_data['emisor'],
                'receptor_input': input_data['receptor'],
                'cuenta_input': input_data['cuenta'],
                'monto_input': input_data['monto'],
                'fecha_consulta': datetime.now().strftime('%Y-%m-%d'),
                'hora_consulta': datetime.now().strftime('%H:%M:%S')
            }
            
            # Guardar en JSON noCEP
            json_file_path = 'consultas/noCEP.json'
            existing_data = []
            if os.path.exists(json_file_path):
                with open(json_file_path, 'r', encoding='utf-8') as f:
                    try:
                        existing_data = json.load(f)
                        if not isinstance(existing_data, list):
                            existing_data = [existing_data]
                    except json.JSONDecodeError:
                        existing_data = []
            
            existing_data.append(no_cep_data)
            with open(json_file_path, 'w', encoding='utf-8') as f:
                json.dump(existing_data, f, ensure_ascii=False, indent=4)
            
            # Guardar en CSV noCEP
            csv_file_path = 'consultas/noCEP.csv'
            file_exists = os.path.exists(csv_file_path)
            
            with open(csv_file_path, 'a', newline='', encoding='utf-8') as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=no_cep_data.keys())
                if not file_exists:
                    writer.writeheader()
                writer.writerow(no_cep_data)
                
            continue
            
        # Descargar el PDF
        pdf = tr.descargar()
        
        # Crear nombre del archivo usando la clave de rastreo y fecha
        nombre_archivo = f"CEP_{tr.fecha_operacion.strftime('%Y%m%d')}_{tr.clave_rastreo}"
        
        # Crear las carpetas necesarias si no existen
        if not os.path.exists('consultas/archivero'):
            os.makedirs('consultas/archivero')
        ruta_consultas = os.path.join('consultas', 'archivero', nombre_archivo)
        
        # Guardar el PDF
        with open(f"{ruta_consultas}.pdf", 'wb') as archivo:
            archivo.write(pdf)
        
        # Extraer texto usando pdfplumber
        with pdfplumber.open(BytesIO(pdf)) as pdf_file:
            texto = pdf_file.pages[0].extract_text()
        
        # Guardar como texto plano
        with open(f"{ruta_consultas}.txt", 'w', encoding='utf-8') as f:
            f.write(texto)
        
        # Función para extraer datos del texto
        def extraer_datos(texto):
            datos = {}
            lines = texto.split('\n')
            i = 0
            while i < len(lines):
                line = lines[i].strip()

                # Extraer instituciones emisora y receptora
                match = re.search(r'Institución emisora del pago\s+(.*?)\s+Institución receptora del pago\s+(.*)', line)
                if match:
                    datos['institucion_emisora'] = match.group(1).strip()
                    datos['institucion_receptora'] = match.group(2).strip()
                    i += 1
                    continue

                # Extraer titulares de la cuenta
                match = re.search(r'Titular de la cuenta\s+(.*?)\s+Titular de la cuenta\s+(.*)', line)
                if match:
                    datos['titular_ordenante'] = match.group(1).strip()
                    datos['titular_beneficiario'] = match.group(2).strip()
                    i += 1
                    continue

                # Extraer RFC/CURP
                match = re.search(r'RFC/CURP\s+(.*?)\s+RFC/CURP\s+(.*)', line)
                if match:
                    datos['rfc_ordenante'] = match.group(1).strip()
                    datos['rfc_beneficiario'] = match.group(2).strip()
                    i += 1
                    continue

                # Extraer CLABE/Tarjeta de débito/Número
                match = re.search(r'CLABE,Tarjeta de débito,Número\s+(\d+)\s+CLABE,Tarjeta de débito,Número\s+(\d+)', line)
                if match:
                    datos['cuenta_ordenante'] = match.group(1).strip()
                    datos['cuenta_beneficiario'] = match.group(2).strip()
                    i += 1
                    continue

                # Procesar otras líneas como antes
                if 'Fecha de consulta' in line:
                    value = line.replace('Fecha de consulta', '').strip()
                    datos['fecha_consulta'] = value
                elif 'Hora de consulta' in line:
                    value = line.replace('Hora de consulta', '').strip()
                    datos['hora_consulta'] = value
                elif 'Fecha de operación en el SPEI' in line and 'Monto' in line:
                    parts = line.split('Monto')
                    fecha_operacion = parts[0].split('Fecha de operación en el SPEI')[-1].strip()
                    fecha_operacion = fecha_operacion.replace('®', '').strip()  # Remover '®' si existe
                    monto = parts[1].replace('$', '').strip()
                    datos['fecha_operacion_spei'] = fecha_operacion
                    datos['monto'] = monto
                elif 'Fecha de abono en la cuenta beneficiaria' in line:
                    if 'IVA' in line:
                        parts = line.split('IVA')
                        fecha_abono = parts[0].replace('Fecha de abono en la cuenta beneficiaria*', '').strip()
                        iva = parts[1].replace('$', '').strip()
                        datos['fecha_abono'] = fecha_abono
                        datos['iva'] = iva
                    else:
                        fecha_abono = line.replace('Fecha de abono en la cuenta beneficiaria*', '').strip()
                        datos['fecha_abono'] = fecha_abono
                elif 'Hora de abono en la cuenta beneficiaria' in line:
                    if 'Referencia numérica' in line:
                        parts = line.split('Referencia numérica')
                        hora_abono = parts[0].replace('Hora de abono en la cuenta beneficiaria*', '').strip()
                        referencia_numerica = parts[1].strip()
                        datos['hora_abono'] = hora_abono
                        datos['referencia_numerica'] = referencia_numerica
                elif 'Concepto del pago' in line:
                    if 'Clave de rastreo' in line:
                        parts = line.split('Clave de rastreo')
                        concepto_pago = parts[0].replace('Concepto del pago', '').strip()
                        clave_rastreo = parts[1].strip()
                        datos['concepto_pago'] = concepto_pago
                        datos['clave_rastreo'] = clave_rastreo
                elif 'Número de Serie del Certificado de Seguridad de la institución receptora del pago' in line:
                    next_line = lines[i+1].strip()
                    datos['numero_serie_certificado'] = next_line
                    i += 1
                elif 'Cadena Original (información del pago):' in line:
                    cadena_original = ''
                    i += 1
                    while i < len(lines) and 'Sello Digital' not in lines[i]:
                        cadena_original += lines[i].strip()
                        i += 1
                    datos['cadena_original'] = cadena_original
                    continue
                elif 'Sello Digital (firma provista por la institución receptora del pago):' in line:
                    sello_digital = ''
                    i += 1
                    while i < len(lines) and lines[i].strip():
                        sello_digital += lines[i].strip()
                        i += 1
                    datos['sello_digital'] = sello_digital

                i += 1
            return datos

        # Extraer datos del texto
        datos_extraidos = extraer_datos(texto)

        # Combinar datos extraídos y datos de entrada
        datos_cep = datos_extraidos.copy()
        datos_cep.update({
            'fecha_input': tr.fecha_operacion.strftime('%Y-%m-%d'),
            'clave_rastreo_input': tr.clave_rastreo,
            'emisor_input': tr.emisor,
            'receptor_input': tr.receptor,
            'cuenta_input': input_data['cuenta'],
            'monto_input': tr.monto,
        })

        # Guardar datos en JSON
        json_file_path = 'consultas/CEP.json'
        existing_data = []
        
        # Leer datos existentes del JSON si existe
        if os.path.exists(json_file_path):
            with open(json_file_path, 'r', encoding='utf-8') as f:
                try:
                    existing_data = json.load(f)
                    if not isinstance(existing_data, list):
                        existing_data = [existing_data]
                except json.JSONDecodeError:
                    existing_data = []
        
        # Agregar nuevo registro
        existing_data.append(datos_cep)
        
        # Guardar JSON actualizado
        with open(json_file_path, 'w', encoding='utf-8') as f:
            json.dump(existing_data, f, ensure_ascii=False, indent=4)

        # Guardar datos en CSV
        csv_file_path = 'consultas/CEP.csv'
        file_exists = os.path.exists(csv_file_path)
        
        with open(csv_file_path, 'a', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=datos_cep.keys())
            if not file_exists:
                writer.writeheader()
            writer.writerow(datos_cep)

        # Después de guardar el PDF y TXT
        print(f"✓ CEP encontrado para clave de rastreo: {input_data['clave_rastreo']}")
        print(f"  └─ PDF y TXT guardados en: consultas/archivero/{nombre_archivo}")

        # Después de extraer y guardar los datos
        print(f"  └─ Datos extraídos y guardados en CEP.json y CEP.csv")
        print(f"     ├─ Fecha operación: {datos_cep.get('fecha_operacion_spei', 'N/A')}")
        print(f"     ├─ Monto: {datos_cep.get('monto', 'N/A')}")
        print(f"     ├─ Ordenante: {datos_cep.get('titular_ordenante', 'N/A')}")
        print(f"     └─ Beneficiario: {datos_cep.get('titular_beneficiario', 'N/A')}")
        print("─" * 80)  # Línea separadora para mejor legibilidad

    except Exception as e:
        print(f"Error procesando el registro {index} con clave de rastreo {input_data['clave_rastreo']}")
        print(f"Tipo de error: {type(e).__name__}")
        print(f"Descripción del error: {str(e)}")
        
        # Si es un error de límite de consultas, esperar más tiempo
        if "429" in str(e) or "too many requests" in str(e).lower():
            wait_time = 60  # esperar 1 minuto
            print(f"Detectado límite de consultas. Esperando {wait_time} segundos...")
            sleep(wait_time)
            continue
        else:
            continue
