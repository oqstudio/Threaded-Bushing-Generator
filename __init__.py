import bpy
import bmesh
import math
import csv
import os
import bpy.utils.previews
import urllib.request
import tempfile

bl_info = {
    "name": "Threaded Bushing Generator",
    "author": "OQStudio (https://oqstudio.github.io)",  # Trik: Adres widać obok autora
    "version": (1, 11),
    "blender": (4, 1, 0),
    "location": "View3D > Sidebar > Generator",
    "description": "Parametric generator for threaded bushings, bolts, and nuts.",
    "doc_url": "https://github.com/oqstudio/Threaded-Bushing-Generator",
    "tracker_url": "https://github.com/oqstudio/Threaded-Bushing-Generator/issues", # Nowy przycisk: Zgłoś błąd
    "category": "Mesh",
}

# --- 0. ZMIENNE GLOBALNE ---
TRANSLATIONS = {} 
LANG_ENUM_ITEMS = [] # Tu dynamicznie trafi lista języków z CSV
preview_collections = {}

# --- FUNKCJE POMOCNICZE ---

def load_data_from_csv():
    """
    Wczytuje CSV, priorytetowo traktując średnik (Excel PL).
    """
    global TRANSLATIONS, LANG_ENUM_ITEMS
    
    csv_path = os.path.join(os.path.dirname(__file__), "slownik.csv")
    TRANSLATIONS = {}
    LANG_ENUM_ITEMS = []
    
    if not os.path.exists(csv_path):
        LANG_ENUM_ITEMS = [('en_US', 'English (Default)', 'Default - File missing')]
        return

    # Lista kodowań do sprawdzenia
    encodings_to_try = ['utf-8-sig', 'cp1250', 'utf-8']
    
    file_content = None
    
    # 1. Próba odczytu pliku
    for enc in encodings_to_try:
        try:
            with open(csv_path, 'r', encoding=enc) as f:
                file_content = f.read()
                # Jeśli plik pusty, idź dalej
                if not file_content.strip(): continue
                break
        except UnicodeDecodeError:
            continue

    if not file_content:
        print("BŁĄD: Nie udało się odczytać pliku (pusty lub złe kodowanie).")
        LANG_ENUM_ITEMS = [('en_US', 'File Error', '')]
        return

    # 2. Parsowanie z wymuszeniem średnika
    from io import StringIO
    
    # Najpierw próbujemy "na sztywno" średnik (dla polskiego Excela)
    try:
        f_mem = StringIO(file_content)
        reader = csv.DictReader(f_mem, delimiter=';')
        headers = [h for h in reader.fieldnames if h and h != 'KEY']
        
        # SPRAWDZENIE: Czy podział zadziałał?
        # Jeśli headers jest pusty LUB pierwsza nazwa jest bardzo długa i ma w sobie przecinki
        # to znaczy, że średnik nie zadziałał (może to plik z USA?)
        if not headers or (len(headers) == 1 and ',' in headers[0]):
            raise ValueError("Chyba to nie średnik...")
            
        # Jak przeszło, to używamy tego readera
        # Musimy go przewinąć/stworzyć od nowa, bo już przeczytaliśmy nagłówki
        f_mem.seek(0)
        reader = csv.DictReader(f_mem, delimiter=';')
        
    except:
        # FALLBACK: Jak średnik zawiódł, próbujemy przecinek
        print("Info: Średnik nie zadziałał, próbuję przecinek...")
        f_mem = StringIO(file_content)
        reader = csv.DictReader(f_mem, delimiter=',')
        headers = [h for h in reader.fieldnames if h and h != 'KEY']

    if not headers:
        LANG_ENUM_ITEMS = [('en_US', 'No Columns Found', '')]
        return

    # 3. Budowanie listy języków
    for lang_code in headers:
        # Usuwamy ewentualne białe znaki (spacje) z nazwy języka
        clean_code = lang_code.strip()
        LANG_ENUM_ITEMS.append((clean_code, clean_code, f"Language: {clean_code}"))
        TRANSLATIONS[clean_code] = {}

    # 4. Wczytywanie słów
    for row in reader:
        if 'KEY' in row and row['KEY']:
            key = row['KEY'].strip() # Usuwamy spacje z klucza
            for lang_code in headers:
                if row.get(lang_code):
                    clean_code = lang_code.strip()
                    TRANSLATIONS[clean_code][key] = row[lang_code]

def get_languages_callback(self, context):
    """Callback zwracający listę języków do panelu"""
    return LANG_ENUM_ITEMS

def get_text(key, context):
    """Funkcja tłumacząca"""
    try:
        # Pobieramy wybrany język z właściwości sceny
        lang_code = context.scene.mech_props_final_v47.language
    except:
        # Jeśli coś nie tak, bierzemy pierwszy dostępny z listy
        lang_code = LANG_ENUM_ITEMS[0][0] if LANG_ENUM_ITEMS else 'en_US'
    
    # Sprawdzamy czy mamy tłumaczenie
    if lang_code in TRANSLATIONS and key in TRANSLATIONS[lang_code]:
        return TRANSLATIONS[lang_code][key]
    
    return key

def load_icons():
    """Ładuje logo z URL lub dysku"""
    pcoll = bpy.utils.previews.new()
    url = "https://oqstudio.github.io/logo.png"
    temp_dir = tempfile.gettempdir()
    cached_logo_path = os.path.join(temp_dir, "oqstudio_logo_cache.png")
    
    icon_loaded = False
    try:
        if not os.path.exists(cached_logo_path):
            import socket
            socket.setdefaulttimeout(3) 
            urllib.request.urlretrieve(url, cached_logo_path)
            
        if os.path.exists(cached_logo_path):
            pcoll.load("my_logo", cached_logo_path, 'IMAGE')
            icon_loaded = True
    except:
        pass # Cicho ignorujemy błąd sieci

    if not icon_loaded:
        icons_dir = os.path.join(os.path.dirname(__file__), "assets")
        local_logo = os.path.join(icons_dir, "logo.png")
        if os.path.exists(local_logo):
            pcoll.load("my_logo", local_logo, 'IMAGE')

    preview_collections["main"] = pcoll

# --- 1. SETUP MATERIAŁÓW ---
def setup_materials(obj):
    mat_data = [
        ("M_Blue", (0.05, 0.2, 0.9, 1.0)),
        ("M_Green", (0.0, 1.0, 0.0, 1.0)),
        ("M_Red", (0.9, 0.05, 0.05, 1.0)),
        ("M_Pink", (1.0, 0.2, 0.7, 1.0)),
        ("M_Orange", (1.0, 0.4, 0.0, 1.0)),
        ("M_White", (1.0, 1.0, 1.0, 1.0))
    ]
    for name, color in mat_data:
        mat = bpy.data.materials.get(name)
        if not mat:
            mat = bpy.data.materials.new(name=name)
            mat.use_nodes = True
            mat.node_tree.nodes.get("Principled BSDF").inputs['Base Color'].default_value = color
            mat.diffuse_color = color 
        if mat.name not in obj.data.materials:
            obj.data.materials.append(mat)

# --- 2. SETUP GWINTU ---
def create_thread(name, parent_obj, radius, height, pitch, thickness, is_internal, segments, offset_z):
    p_name = "Thread_Profile_Curve_v47"
    if p_name in bpy.data.curves:
        bpy.data.curves.remove(bpy.data.curves[p_name], do_unlink=True)
    
    p_data = bpy.data.curves.new(p_name, type='CURVE')
    p_data.dimensions = '2D'
    spline = p_data.splines.new('POLY')
    spline.points.add(3)
    dx = -1 if is_internal else 1
    
    spline.points[0].co = (0, thickness * 0.7, 0, 1)
    spline.points[1].co = (thickness * dx, 0, 0, 1)
    spline.points[2].co = (0, -thickness * 0.7, 0, 1)
    spline.points[3].co = (thickness * -0.2 * dx, 0, 0, 1)
    spline.use_cyclic_u = True
    p_obj = bpy.data.objects.new(p_name, p_data)
    bpy.context.collection.objects.link(p_obj)
    p_obj.hide_viewport = p_obj.hide_render = True

    h_safe = height - 0.8
    turns = max(0.1, h_safe / pitch)
    c_data = bpy.data.curves.new(name=f"{name}_C", type='CURVE')
    c_data.dimensions = '3D'
    c_data.twist_mode = 'Z_UP'
    c_data.bevel_mode = 'OBJECT'
    c_data.bevel_object = p_obj
    c_data.use_fill_caps = True
    
    poly = c_data.splines.new('BEZIER')
    pts_turn = int(segments / 2)
    t_pts = max(2, int(turns * pts_turn))
    poly.bezier_points.add(t_pts - 1)
    
    for i in range(t_pts):
        t = i / (t_pts - 1)
        ang = t * turns * 2 * math.pi
        bp = poly.bezier_points[i]
        bp.co = (math.cos(ang) * radius, math.sin(ang) * radius, 0.4 + (t * h_safe))
        bp.handle_left_type = bp.handle_right_type = 'AUTO'
        bp.radius = (i/pts_turn) if i < pts_turn else ((t_pts-i)/pts_turn if i > t_pts-pts_turn else 1.0)

    c_obj = bpy.data.objects.new(f"{name}_Th", c_data)
    bpy.context.collection.objects.link(c_obj)
    c_obj.location.x = parent_obj.location.x
    c_obj.location.y = parent_obj.location.y
    c_obj.location.z = parent_obj.location.z + offset_z
    
    bpy.context.view_layer.objects.active = c_obj
    c_obj.select_set(True)
    bpy.ops.object.convert(target='MESH')
    th_mesh = bpy.context.active_object
    for p in th_mesh.data.polygons: p.use_smooth = False
    
    c_obj.data.materials.clear()
    for mat in parent_obj.data.materials: c_obj.data.materials.append(mat)
    for p in th_mesh.data.polygons: p.material_index = 1 
        
    bpy.ops.object.select_all(action='DESELECT')
    parent_obj.select_set(True)
    th_mesh.select_set(True)
    bpy.context.view_layer.objects.active = parent_obj
    bpy.ops.object.join()
    bpy.data.objects.remove(p_obj, do_unlink=True)

# --- 3. GEOMETRIA GŁÓWNA ---
def build_part(name, x_pos, is_bolt, props):
    fi_user = props.radius 
    radius_outer_nut = fi_user / 2.0
    th_wall = props.thickness 
    cl = props.clearance       
    t_s = props.thread_size    
    nut_inner_wall_radius = radius_outer_nut - th_wall
    head_outer_radius_ref = radius_outer_nut 

    if not is_bolt:
        r_out = radius_outer_nut
        r_in = nut_inner_wall_radius
        r_base_thread = r_in 
    else:
        bolt_peak = nut_inner_wall_radius - cl
        r_base_thread = bolt_peak - t_s
        r_out = r_base_thread
        r_in = r_out - th_wall
        
    r_wash = head_outer_radius_ref + props.washer_radius
    h_t, h_w = props.height, props.washer_height
    seg = props.segments

    if name in bpy.data.objects:
        bpy.data.objects.remove(bpy.data.objects[name], do_unlink=True)

    mesh = bpy.data.meshes.new(name + "_Mesh")
    obj = bpy.data.objects.new(name, mesh)
    obj.location.x = x_pos
    bpy.context.collection.objects.link(obj)

    setup_materials(obj)
    bm = bmesh.new()
    
    circle = bmesh.ops.create_circle(bm, cap_ends=False, radius=r_in, segments=seg)
    ed_in = [e for e in bm.edges if all(v in circle['verts'] for v in e.verts)]
    
    ex = bmesh.ops.extrude_edge_only(bm, edges=ed_in)
    v_wash_bot = [v for v in ex['geom'] if isinstance(v, bmesh.types.BMVert)]
    bmesh.ops.scale(bm, vec=(r_wash/r_in, r_wash/r_in, 1.0), verts=v_wash_bot)
    for f in [f for f in ex['geom'] if isinstance(f, bmesh.types.BMFace)]: f.material_index = 5
    
    ex = bmesh.ops.extrude_edge_only(bm, edges=[e for e in bm.edges if all(v in v_wash_bot for v in e.verts)])
    v_wash_top = [v for v in ex['geom'] if isinstance(v, bmesh.types.BMVert)]
    bmesh.ops.translate(bm, vec=(0, 0, h_w), verts=v_wash_top)
    for f in [f for f in ex['geom'] if isinstance(f, bmesh.types.BMFace)]: f.material_index = 4

    target_top_radius = head_outer_radius_ref
    ex = bmesh.ops.extrude_edge_only(bm, edges=[e for e in bm.edges if all(v in v_wash_top for v in e.verts)])
    v_out_mid = [v for v in ex['geom'] if isinstance(v, bmesh.types.BMVert)]
    bmesh.ops.scale(bm, vec=(target_top_radius/r_wash, target_top_radius/r_wash, 1.0), verts=v_out_mid)
    for f in [f for f in ex['geom'] if isinstance(f, bmesh.types.BMFace)]: f.material_index = 2

    ex = bmesh.ops.extrude_edge_only(bm, edges=[e for e in bm.edges if all(v in v_out_mid for v in e.verts)])
    v_stem_base = [v for v in ex['geom'] if isinstance(v, bmesh.types.BMVert)]
    bmesh.ops.scale(bm, vec=(r_out/target_top_radius, r_out/target_top_radius, 1.0), verts=v_stem_base)
    for f in [f for f in ex['geom'] if isinstance(f, bmesh.types.BMFace)]: f.material_index = 2 

    ex = bmesh.ops.extrude_edge_only(bm, edges=[e for e in bm.edges if all(v in v_stem_base for v in e.verts)])
    v_out_top = [v for v in ex['geom'] if isinstance(v, bmesh.types.BMVert)]
    bmesh.ops.translate(bm, vec=(0, 0, h_t), verts=v_out_top)
    for f in [f for f in ex['geom'] if isinstance(f, bmesh.types.BMFace)]: f.material_index = 0

    ex = bmesh.ops.extrude_edge_only(bm, edges=[e for e in bm.edges if all(v in v_out_top for v in e.verts)])
    v_in_top = [v for v in ex['geom'] if isinstance(v, bmesh.types.BMVert)]
    bmesh.ops.scale(bm, vec=(r_in/r_out, r_in/r_out, 1.0), verts=v_in_top)
    for f in [f for f in ex['geom'] if isinstance(f, bmesh.types.BMFace)]: f.material_index = 3

    ex = bmesh.ops.extrude_edge_only(bm, edges=[e for e in bm.edges if all(v in v_in_top for v in e.verts)])
    v_in_bot = [v for v in ex['geom'] if isinstance(v, bmesh.types.BMVert)]
    bmesh.ops.translate(bm, vec=(0, 0, -(h_t + h_w)), verts=v_in_bot)
    for f in [f for f in ex['geom'] if isinstance(f, bmesh.types.BMFace)]: f.material_index = 5
    
    ex_bridge = bmesh.ops.bridge_loops(bm, edges=[e for e in bm.edges if all(v in v_in_bot for v in e.verts)] + ed_in)
    for f in ex_bridge['faces']: f.material_index = 5
        
    bm.to_mesh(mesh)
    bm.free()
    for p in obj.data.polygons: p.use_smooth = False
    create_thread(f"T_{name}", obj, r_base_thread, h_t, props.thread_pitch, t_s, not is_bolt, seg, h_w)

# --- 4. PANEL I DANE ---
class MECH_FINAL_Props_v47(bpy.types.PropertyGroup):
    # Dynamiczny wybór języka
    language: bpy.props.EnumProperty(
        name="Language",
        description="Select Panel Language / Wybierz język",
        items=get_languages_callback # Tu jest MAGIA - funkcja zamiast listy
    )
    segments: bpy.props.IntProperty(name="Segments", default=64, min=8)
    radius: bpy.props.FloatProperty(name="Radius", default=40.0)
    height: bpy.props.FloatProperty(name="Height", default=50.0)
    thickness: bpy.props.FloatProperty(name="Thickness", default=2.0)
    thread_size: bpy.props.FloatProperty(name="Thread Size", default=3.0)
    thread_pitch: bpy.props.FloatProperty(name="Thread Pitch", default=5.0)
    clearance: bpy.props.FloatProperty(name="Clearance", default=0.2)
    washer_radius: bpy.props.FloatProperty(name="Washer Radius", default=20.0)
    washer_height: bpy.props.FloatProperty(name="Washer Height", default=5.0)

# --- 5. PREFERENCJE ADDONA ---
class MECH_FINAL_Preferences(bpy.types.AddonPreferences):
    bl_idname = __package__ 

    def draw(self, context):
        layout = self.layout
        pcoll = preview_collections.get("main")
        if pcoll and "my_logo" in pcoll:
            row = layout.row()
            row.alignment = 'CENTER'
            row.template_icon(icon_value=pcoll["my_logo"].icon_id, scale=5.0) 
        
        layout.label(text="Threaded Bushing Generator by OQStudio", icon='INFO')
        layout.separator()
        
        box = layout.box()
        box.label(text="Description / Opis:")
        box.label(text="Professional parametric tool for generating threaded bushings, bolts, and nuts.")
        box.label(text="Features precise control over thread pitch, clearance, diameter, and washer dimensions.")
        # Usunąłem stąd listę języków. 
        box.label(text="Languages are detected automatically from slownik.csv.")
        box.separator()
        box.label(text="To use: Go to 3D View > Sidebar (N) > Generator tab.")

class MECH_FINAL_OT_Execute(bpy.types.Operator):
    bl_idname = "mesh.mech_gen_exec_final"
    bl_label = "Generate" 
    def execute(self, context):
        p = context.scene.mech_props_final_v47
        build_part("Nakretka", 0, False, p)
        build_part("Sruba", -(p.radius * 2.5), True, p)
        for area in context.screen.areas:
            if area.type == 'VIEW_3D': area.spaces.active.shading.color_type = 'MATERIAL'
        return {'FINISHED'}

class MECH_FINAL_PT_Panel(bpy.types.Panel):
    bl_idname = "MECH_GEN_PT_FinalPanel_v47"
    bl_space_type, bl_region_type, bl_category = 'VIEW_3D', 'UI', 'Generator'
    bl_label = "Threaded Bushing"

    def draw(self, context):
        def msg(key): return get_text(key, context)
        p = context.scene.mech_props_final_v47
        l = self.layout
        
        # LOGO
        pcoll = preview_collections.get("main")
        if pcoll and "my_logo" in pcoll:
            row = l.row(); row.alignment = 'CENTER'
            row.template_icon(icon_value=pcoll["my_logo"].icon_id, scale=8.0)
            l.separator()

        # LANGUAGE SWITCH
        row = l.row(align=True); row.alignment = 'RIGHT'
        row.prop(p, "language", text="") 
        l.separator()

        # UI
        l.label(text=msg("label_bushing"))
        row = l.row(align=True)
        row.label(icon='COLORSET_04_VEC'); row.prop(p, "radius", text=msg("radius")) 
        row = l.row(align=True)
        row.label(icon='COLORSET_04_VEC'); row.prop(p, "height", text=msg("height"))
        row = l.row(align=True)
        row.label(icon='COLORSET_06_VEC'); row.prop(p, "thickness", text=msg("thickness"))
        l.prop(p, "segments", icon='STRANDS', text=msg("segments"))
        l.separator()
        
        l.label(text=msg("label_thread"))
        row = l.row(align=True)
        row.label(icon='COLORSET_03_VEC'); row.prop(p, "thread_size", text=msg("thread_size"))
        row = l.row(align=True)
        row.label(icon='COLORSET_03_VEC'); row.prop(p, "thread_pitch", text=msg("thread_pitch"))
        row = l.row(align=True)
        row.label(icon='COLORSET_03_VEC'); row.prop(p, "clearance", text=msg("clearance"))
        l.separator()
        
        l.label(text=msg("label_washer"))
        row = l.row(align=True)
        row.label(icon='COLORSET_01_VEC'); row.prop(p, "washer_radius", text=msg("washer_radius"))
        row = l.row(align=True)
        row.label(icon='COLORSET_02_VEC'); row.prop(p, "washer_height", text=msg("washer_height"))
        l.separator()
        
        l.operator("mesh.mech_gen_exec_final", icon='MOD_SCREW', text=msg("op_generate"))

def register():
    load_icons()
    load_data_from_csv() # Wczytuje języki PRZED rejestracją klas
    bpy.utils.register_class(MECH_FINAL_Preferences)
    bpy.utils.register_class(MECH_FINAL_Props_v47)
    bpy.utils.register_class(MECH_FINAL_OT_Execute)
    bpy.utils.register_class(MECH_FINAL_PT_Panel)
    bpy.types.Scene.mech_props_final_v47 = bpy.props.PointerProperty(type=MECH_FINAL_Props_v47)

def unregister():
    for pcoll in preview_collections.values():
        bpy.utils.previews.remove(pcoll)
    preview_collections.clear()
    bpy.utils.unregister_class(MECH_FINAL_Preferences)
    bpy.utils.unregister_class(MECH_FINAL_Props_v47)
    bpy.utils.unregister_class(MECH_FINAL_OT_Execute)
    bpy.utils.unregister_class(MECH_FINAL_PT_Panel)
    if hasattr(bpy.types.Scene, "mech_props_final_v47"):
        del bpy.types.Scene.mech_props_final_v47

if __name__ == "__main__":
    try: unregister()
    except: pass

    register()
