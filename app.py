import streamlit as st
import pandas as pd
import json
import re

# Configuración de la página
st.set_page_config(
    page_title="WMS 3D - Mapeo de Bulbos",
    page_icon="❄️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Título y Descripción
st.title("❄️ Mapeo Bulbos FSJ ❄️")
st.markdown(""" Los Latidos Representan a Los Pallets Duplicados """)

# Cargar y procesar datos de Excel
@st.cache_data(ttl=60)
def load_data():
    try:
        df = pd.read_excel('MAPEO BULBOS.xlsx')
        # Filtrar filas que contengan una posición válida
        df_clean = df[df['Posicion'].notna()].copy()
        
        # Expresión regular para descomponer posiciones como: C1HA11, C2OA24, etc.
        pattern = re.compile(r'^C(\d+)([HO])([A-Z])(\d+)(\d+)$')
        
        parsed_data = []
        for idx, row in df_clean.iterrows():
            pos_str = str(row['Posicion']).strip()
            match = pattern.match(pos_str)
            if match:
                camara = int(match.group(1))
                sector = match.group(2)      # H o O
                hilera = match.group(3)      # Hilera (A a M)
                nivel = int(match.group(4))   # Nivel (Altura 1 a 4)
                modulo = int(match.group(5))  # Módulo (Profundidad lateral 1 a 5)
                
                parsed_data.append({
                    'Exportadora': row['Exportadora'],
                    'Pallet': str(row['Pallet']),
                    'Lote': str(row['Lote']),
                    'Tipo': str(row['Tipo']) if pd.notna(row['Tipo']) else '',
                    'Variedad': row['Variedad'].split('(')[0].strip() if '(' in str(row['Variedad']) else str(row['Variedad']),
                    'Cantidad': row['Cantidad'],
                    'KN': row['KN'],
                    'Posicion': pos_str,
                    'Camara': f"Cámara {camara}",
                    'Sector': "Sector H (Huape)" if sector == 'H' else "Sector O (Oro Verde)",
                    'Hilera': hilera,
                    'Modulo': modulo,
                    'Nivel': nivel
                })
        
        return pd.DataFrame(parsed_data), df
    except Exception as e:
        st.error(f"Error al cargar el archivo Excel: {e}")
        return pd.DataFrame(), pd.DataFrame()

df_parsed, df_raw = load_data()

if df_parsed.empty:
    st.warning("No se encontraron registros válidos en 'MAPEO BULBOS.xlsx'. Asegúrate de que el archivo esté en la misma carpeta.")
    st.stop()

# --- CONSTANTES DE DISEÑO FÍSICO REAL ---
HILERAS = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M'] # 13 Hileras hacia el fondo
SECTORES = ['H', 'O'] # Lados de la cámara
PROFUNDIDAD_MAX = 5  # 5 Módulos laterales hacia la izquierda/derecha
ALTURA_MAX = 4       # 4 Niveles de altura
POSICIONES_TOTALES_POR_CAMARA = len(HILERAS) * len(SECTORES) * PROFUNDIDAD_MAX * ALTURA_MAX # 520 posiciones

# Sidebar - Filtros
st.sidebar.header("🔍 Filtros de Visualización")
camaras_disponibles = sorted(df_parsed['Camara'].unique())
camara_seleccionada = st.sidebar.selectbox("Selecciona Cámara", camaras_disponibles)

variedades_disponibles = ["Todas"] + sorted(df_parsed['Variedad'].unique())
variedad_seleccionada = st.sidebar.selectbox("Variedad de Bulbo", variedades_disponibles)

racks_disponibles = ["Todos"] + sorted(df_parsed['Hilera'].unique())
rack_seleccionado = st.sidebar.selectbox("Selecciona Rack", racks_disponibles)

# Filtrar Datos por la Cámara Seleccionada
df_camara = df_parsed[df_parsed['Camara'] == camara_seleccionada]

# --- CÁLCULO DE MÉTRICAS (KPIs) ---
pallets_ocupados = len(df_camara)
espacios_vacios = POSICIONES_TOTALES_POR_CAMARA - pallets_ocupados

posiciones_counts = df_camara['Posicion'].value_counts()
duplicados = int((posiciones_counts[posiciones_counts > 1] - 1).sum())
posiciones_con_multiples = int((posiciones_counts > 1).sum())

# Mostrar Indicadores en Pantalla
st.write("---")
kpi1, kpi2, kpi3, kpi4 = st.columns(4)

with kpi1:
    st.metric(
        "Capacidad de la Cámara", 
        f"{POSICIONES_TOTALES_POR_CAMARA} slots", 
        help="Estructura física real: 13 racks (A-M) x 2 lados (H, O) x 5 de profundidad lateral x 4 de altura = 520."
    )
with kpi2:
    st.metric(
        "Pallets Ocupados", 
        f"{pallets_ocupados} un.", 
        f"{((pallets_ocupados/POSICIONES_TOTALES_POR_CAMARA)*100):.1f}% Ocupación"
    )
with kpi3:
    st.metric(
        "Espacios Vacíos", 
        f"{espacios_vacios} un.", 
        f"{((espacios_vacios/POSICIONES_TOTALES_POR_CAMARA)*100):.1f}% Disponible", 
        delta_color="inverse"
    )
with kpi4:
    st.metric(
        "Misma Posición (Sobre-apilado)", 
        f"{duplicados} un.", 
        help=f"Existen {posiciones_con_multiples} ubicaciones del excel que tienen más de un pallet asignado al mismo casillero exacto."
    )

# Filtrar Datos por variedad si aplica
df_filtered = df_camara
if variedad_seleccionada != "Todas":
    df_filtered = df_filtered[df_filtered['Variedad'] == variedad_seleccionada]
if rack_seleccionado != "Todos":
    df_filtered = df_filtered[df_filtered['Hilera'] == rack_seleccionado]

# Mapeo de letra de rack a coordenada longitudinal (Z)
hilera_map = {char: idx for idx, char in enumerate(HILERAS)}

# --- IDENTIFICACIÓN DE POSICIONES DUPLICADAS ---
pos_counts = df_filtered['Posicion'].value_counts()
duplicated_positions = pos_counts[pos_counts > 1].index.tolist()

# Preparar datos de pallets para render 3D con la NUEVA rotación
threejs_data = []
for _, row in df_filtered.iterrows():
    # Eje Z = Hileras / Racks (A-M se extienden longitudinalmente hacia el fondo)
    z_coord = hilera_map.get(row['Hilera'], 0) * 4.5  # Separación cómoda entre racks en profundidad
    
    # Eje X = Módulos (Se abren lateralmente hacia la izquierda o derecha del pasillo central)
    # Dejamos un espacio libre en el centro (X=0) para el pasillo central.
    x_offset = row['Modulo'] * 3.2 + 4.0  # El offset se incrementa a medida que el módulo aumenta
    
    if "Sector O" in row['Sector']:
        x_coord = -x_offset  # Sector Oeste: Izquierda (Coordenadas X negativas)
    else:
        x_coord = x_offset   # Sector Helada: Derecha (Coordenadas X positivas)
        
    # Eje Y = Altura (Niveles del 1 al 4)
    y_coord = (row['Nivel'] - 1) * 2.2
    
    # Generar color según la variedad
    color_hash = hash(row['Variedad']) % 0xffffff
    color_hex = f"#{color_hash:06x}"
    
    threejs_data.append({
        'pos': row['Posicion'],
        'pallet': row['Pallet'],
        'lote': row['Lote'],
        'tipo': row['Tipo'],
        'variedad': row['Variedad'],
        'cantidad': int(row['Cantidad']),
        'x': x_coord,
        'y': y_coord,
        'z': z_coord,
        'color': color_hex,
        'duplicate': row['Posicion'] in duplicated_positions
    })

threejs_data_json = json.dumps(threejs_data)

# --- VISUALIZADOR GEOMÉTRICO 3D CON THREE.JS ---
html_template = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <style>
        body { margin: 0; padding: 0; overflow: hidden; background-color: #111115; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; }
        #canvas-container { width: 100vw; height: 600px; position: relative; }
        #tooltip {
            position: absolute;
            background: rgba(15, 23, 42, 0.95);
            color: #f8fafc;
            padding: 14px 18px;
            border-radius: 8px;
            border: 1px solid #38bdf8;
            display: none;
            pointer-events: none;
            font-size: 13px;
            z-index: 100;
            box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.5), 0 4px 6px -4px rgba(0, 0, 0, 0.5);
            line-height: 1.6;
        }
        #legend {
            position: absolute;
            bottom: 15px;
            left: 15px;
            background: rgba(15, 23, 42, 0.85);
            padding: 12px;
            color: #fff;
            font-size: 11px;
            border-radius: 6px;
            max-height: 200px;
            overflow-y: auto;
            border: 1px solid #334155;
        }
        .legend-item { display: flex; align-items: center; margin-bottom: 6px; }
        .legend-color { width: 12px; height: 12px; margin-right: 8px; border-radius: 3px; }
        #aisle-label {
            position: absolute;
            top: 15px;
            left: 50%;
            transform: translateX(-50%);
            background: rgba(15, 23, 42, 0.9);
            color: #38bdf8;
            padding: 8px 18px;
            border-radius: 20px;
            font-size: 13px;
            font-weight: bold;
            border: 1px solid #38bdf8;
            letter-spacing: 0.5px;
        }
    </style>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/controls/OrbitControls.js"></script>
</head>
<body>
    <div id="canvas-container">
        <div id="aisle-label">🚦 PASILLO CENTRAL LONGITUDINAL (LADO O ⟵  🛩️  ⟶ LADO H)</div>
        <div id="tooltip"></div>
        <div id="legend">
            <strong>Variedades de Bulbo</strong>
            <div id="legend-items"></div>
        </div>
    </div>

    <script>
        const palletsData = __THREEJS_DATA__;
        const container = document.getElementById('canvas-container');
        const scene = new THREE.Scene();
        scene.background = new THREE.Color(0x0f172a); 

        // Cámara colocada para ver hacia el fondo de la bodega a lo largo del pasillo
        const camera = new THREE.PerspectiveCamera(40, window.innerWidth / 600, 0.1, 1000);
        camera.position.set(0, 35, 75);

        const renderer = new THREE.WebGLRenderer({ antialias: true });
        renderer.setSize(window.innerWidth, 600);
        container.appendChild(renderer.domElement);

        const controls = new THREE.OrbitControls(camera, renderer.domElement);
        controls.enableDamping = true;
        controls.dampingFactor = 0.05;
        controls.maxPolarAngle = Math.PI / 2 - 0.05;
        // Enfocar el punto central de la bodega (X=0, Y=4, Z=medio de racks)
        controls.target.set(0, 4, 27);

        // Iluminación
        scene.add(new THREE.AmbientLight(0xffffff, 0.65));
        const dirLight1 = new THREE.DirectionalLight(0xffffff, 0.6);
        dirLight1.position.set(15, 60, 15);
        scene.add(dirLight1);
        
        const dirLight2 = new THREE.DirectionalLight(0x38bdf8, 0.4); 
        dirLight2.position.set(-30, 20, -10);
        scene.add(dirLight2);

        // Grilla del Piso
        const gridHelper = new THREE.GridHelper(150, 50, 0x38bdf8, 0x1e293b);
        gridHelper.position.y = -0.9;
        scene.add(gridHelper);

        // Pasillo Central Físico (corre sobre el eje Z desde Z = -5 hasta Z = 60)
        const laneGeo = new THREE.PlaneGeometry(7.5, 70);
        const laneMat = new THREE.MeshBasicMaterial({ color: 0x1e293b, side: THREE.DoubleSide });
        const lane = new THREE.Mesh(laneGeo, laneMat);
        lane.rotation.x = Math.PI / 2;
        lane.position.set(0, -0.88, 27); 
        scene.add(lane);

        // Geometrías para Racks y Pallets
        const HILERAS_LIST = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M'];
        const geometry = new THREE.BoxGeometry(2.2, 1.6, 2.2); 
        const rackGeometry = new THREE.BoxGeometry(2.5, 0.06, 2.5); 
        const rackMaterial = new THREE.MeshStandardMaterial({ color: 0x475569, metalness: 0.8, roughness: 0.2 });

        function createTextTexture(text) {
            const canvas = document.createElement('canvas');
            canvas.width = 256;
            canvas.height = 128;
            const ctx = canvas.getContext('2d');
            ctx.fillStyle = '#1e293b'; 
            ctx.fillRect(0, 0, 256, 128);
            ctx.font = 'Bold 80px sans-serif';
            ctx.fillStyle = '#38bdf8'; 
            ctx.textAlign = 'center';
            ctx.textBaseline = 'middle';
            ctx.fillText(text, 128, 64);
            return new THREE.CanvasTexture(canvas);
        }

        // Generación de Racks Vacíos con la nueva rotación
        HILERAS_LIST.forEach((hilera, hIdx) => {
            const z_coord = hIdx * 4.5; // Posición hacia el fondo
            
            // Generar los dos sectores laterales (Oeste a la izquierda, Helada a la derecha)
            const sides = [
                { name: 'O', sign: -1 }, 
                { name: 'H', sign: 1 }   
            ];

            sides.forEach(side => {
                // Dibujar soportes estructurales para los 5 módulos horizontales laterales
                for (let modulo = 1; modulo <= 5; modulo++) {
                    const x_coord = side.sign * (modulo * 3.2 + 4.0);
                    
                    for (let level = 1; level <= 4; level++) {
                        const shelf = new THREE.Mesh(rackGeometry, rackMaterial);
                        shelf.position.set(x_coord, (level - 1) * 2.2 - 0.85, z_coord);
                        scene.add(shelf);
                    }
                }

                // Colocar cartel identificador de la Hilera/Rack a la orilla del pasillo central (Módulo 1)
                const labelTexture = createTextTexture(`${hilera}${side.name}`);
                const labelMaterial = new THREE.MeshBasicMaterial({ map: labelTexture, side: THREE.DoubleSide });
                const labelGeometry = new THREE.PlaneGeometry(2.2, 1.1);
                const labelMesh = new THREE.Mesh(labelGeometry, labelMaterial);
                
                // Ubicado justo al borde del pasillo, viendo hacia el centro
                const labelX = side.sign * 5.8;
                labelMesh.position.set(labelX, 0.2, z_coord);
                labelMesh.rotation.y = side.sign * (Math.PI / 2); // Rotado para ver hacia el pasillo
                scene.add(labelMesh);
            });
        });

        // Renderizado de Pallets
        const meshes = [];
        const legendMap = new Map();

        palletsData.forEach(p => {
            const materialParams = {
                color: new THREE.Color(p.color),
                roughness: 0.3,
                metalness: 0.1
            };
            
            if (p.duplicate) {
                materialParams.emissive = new THREE.Color(0xff3333);
                materialParams.emissiveIntensity = 0.3;
            }
            
            const material = new THREE.MeshStandardMaterial(materialParams);
            const mesh = new THREE.Mesh(geometry, material);
            mesh.position.set(p.x, p.y, p.z);
            mesh.userData = p; 
            scene.add(mesh);
            meshes.push(mesh);
            legendMap.set(p.variedad, p.color);
        });

        // Generar Leyenda dinámica
        const legendContainer = document.getElementById('legend-items');
        legendMap.forEach((color, variety) => {
            const item = document.createElement('div');
            item.className = 'legend-item';
            item.innerHTML = `<div class="legend-color" style="background-color: ${color}"></div><span>${variety}</span>`;
            legendContainer.appendChild(item);
        });

        // Raycasting interactivo para Tooltip
        const raycaster = new THREE.Raycaster();
        const mouse = new THREE.Vector2();
        const tooltip = document.getElementById('tooltip');

        function onMouseMove(event) {
            const rect = renderer.domElement.getBoundingClientRect();
            mouse.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
            mouse.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
            
            if (tooltip.style.display === 'block') {
                tooltip.style.left = (event.clientX + 15) + 'px';
                tooltip.style.top = (event.clientY + 15) + 'px';
            }
        }

        window.addEventListener('mousemove', onMouseMove, false);

        // Animación principal
        function animate() {
            requestAnimationFrame(animate);
            controls.update();

            // Efecto de Latido en duplicados
            const time = Date.now() * 0.005;
            const pulseScale = 1.0 + Math.sin(time) * 0.08;
            const pulseEmissive = 0.15 + (Math.sin(time) + 1) / 2 * 0.45;

            meshes.forEach(m => {
                if (m.userData.duplicate) {
                    m.scale.set(pulseScale, pulseScale, pulseScale);
                    if (m.material.emissive) {
                        m.material.emissiveIntensity = pulseEmissive;
                    }
                }
            });

            raycaster.setFromCamera(mouse, camera);
            const intersects = raycaster.intersectObjects(meshes);

            if (intersects.length > 0) {
                const target = intersects[0].object.userData;
                tooltip.style.display = 'block';
                tooltip.innerHTML = `
                    <div style="border-bottom: 1px solid #38bdf8; padding-bottom: 5px; margin-bottom: 8px;">
                        <strong style="color: #38bdf8; font-size: 14px;">📍 Ubicación: ${target.pos}</strong>
                    </div>
                    📦 <strong>N° de Pallet:</strong> ${target.pallet}<br/>
                    🔢 <strong>Lote:</strong> ${target.lote}<br/>
                    🌿 <strong>Tipo:</strong> ${target.tipo}<br/>
                    🏷️ <strong>Variedad:</strong> ${target.variedad}<br/>
                    📊 <strong>Cantidad:</strong> ${target.cantidad} un.
                `;
                document.body.style.cursor = 'pointer';
            } else {
                tooltip.style.display = 'none';
                document.body.style.cursor = 'default';
            }

            renderer.render(scene, camera);
        }
        animate();

        window.addEventListener('resize', () => {
            camera.aspect = window.innerWidth / 600;
            camera.updateProjectionMatrix();
            renderer.setSize(window.innerWidth, 600);
        });
    </script>
</body>
</html>
"""

# Inyectamos los datos reemplazando la palabra clave
html_final = html_template.replace("__THREEJS_DATA__", threejs_data_json)

# Renderizar en Streamlit
st.components.v1.html(html_final, height=620)

# Explorador de datos tradicional al fondo
st.markdown("### 📊 Inventario Físico")
st.dataframe(df_filtered[['Posicion', 'Pallet', 'Lote', 'Tipo', 'Variedad', 'Cantidad', 'KN', 'Sector']], use_container_width=True)
