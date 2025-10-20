"""
chk_dimension.py
DXF 파일 분석 모듈 - 치수/주석 정보 추출 및 분석

CAD-Work 프로젝트
버전: 1.1
"""

import ezdxf
import math
from datetime import datetime
from collections import defaultdict
from itertools import combinations


# ============================================================================
# 설정 (Configuration)
# ============================================================================

# 파일 경로 설정 (직접 지정)
#INPUT_FILE = "data\\gear-disk\\Gear Disk dxf File.dxf"  # 분석할 DXF 파일
INPUT_FILE = "data\\doosan\\test-002.dxf"  # 분석할 DXF 파일
OUTPUT_REPORT = "analysis_report.txt"  # 출력 보고서 파일명

ON_DETECT_EX_LEADERS = False  # 지시선이 아닌 직선을 대상으로 지시선의 역할을 찾는다

# 화살표 탐지 설정
CONFIG = {
    'ARROW_DETECTION': {
        'tip_point_tolerance': 0.1,     # 3개 점이 만나는 허용 오차 (mm)
        'barb_length_diff_max': 0.2,    # 대칭선 길이 차이 허용 오차 (mm)
        'arrow_angle_max': 75.0,        # 주축선과 대칭선 최대 각도 (도)
        'barb_angle_diff_max': 0.5,     # 두 대칭선 각도 차이 허용 오차 (도)
    },
    'ARROW_CONNECTED_LINE': {
        'max_gap': 3.0,                 # 직선 연결 최대 간격 (mm)
        'angle_tolerance': 5.0,         # 각도 허용 오차 (도)
    },
    'LEADER_ARROW_MATCHING': {
        'max_distance': 10.0,           # 텍스트 매칭 최대 거리 (mm)
    },
    'LEADER_BOUNDARY_MATCHING': {
        'max_distance_to_arrow': 5.0,   # 화살표와 경계선 최대 거리 (mm)
        'perpendicular_angle_min': 89.5, # 직각 최소 각도 (도)
        'perpendicular_angle_max': 90.5, # 직각 최대 각도 (도)
    }
}


# ============================================================================
# 데이터 클래스 (Data Classes)
# ============================================================================

class Point:
    """점 좌표"""
    def __init__(self, x, y):
        self.x = x
        self.y = y
    
    def __repr__(self):
        return f"({self.x:.2f}, {self.y:.2f})"


class Line:
    """선분"""
    def __init__(self, start, end, handle=None, layer=None, color=None, lineweight=None, linetype=None, line_id=None):
        self.start_point = start if isinstance(start, Point) else Point(start[0], start[1])
        self.end_point = end if isinstance(end, Point) else Point(end[0], end[1])
        self.handle = handle
        self.layer = layer
        self.color = color          # 색상 번호 (1-255) 또는 None
        self.lineweight = lineweight  # 선 두께 (-3=기본, -2=bylayer, -1=byblock, 0-211=실제값)
        self.linetype = linetype     # 선 종류 (Continuous, Dashed 등)
        self.id = line_id           # 라인 ID (배열 인덱스 기반)
    
    def __repr__(self):
        return f"Line[ID:{self.id}, {self.start_point} → {self.end_point}]"


class Arrow:
    """화살표 (주축선 + 화살촉)"""
    def __init__(self, shaft, left_barb, right_barb, tip_point, direction='end'):
        self.shaft = shaft
        self.left_barb = left_barb
        self.right_barb = right_barb
        self.tip_point = tip_point
        self.direction = direction  # 'start' | 'end'
        self.id = None
    
    def __repr__(self):
        return f"Arrow[tip={self.tip_point}, dir={self.direction}]"


class TextEntity:
    """텍스트 엔티티"""
    def __init__(self, handle, content, position, layer, entity_type='TEXT',
                 color=None, style=None, height=None, rotation=None, 
                 width=None, halign=None, valign=None,
                 char_height=None, line_spacing_factor=None, attachment_point=None):
        self.handle = handle
        self.content = content
        self.position = position if isinstance(position, Point) else Point(position[0], position[1])
        self.layer = layer
        self.entity_type = entity_type
        
        # 공통 속성
        self.color = color              # 색상 번호
        self.style = style              # 텍스트 스타일 이름 (폰트 정보)
        self.rotation = rotation        # 회전 각도 (도 단위)
        
        # TEXT 전용 속성
        self.height = height            # 텍스트 높이
        self.width = width              # 폭 배율 (TEXT) 또는 텍스트 박스 너비 (MTEXT)
        self.halign = halign            # 수평 정렬
        self.valign = valign            # 수직 정렬
        
        # MTEXT 전용 속성
        self.char_height = char_height  # 문자 높이
        self.line_spacing_factor = line_spacing_factor  # 줄 간격 배율
        self.attachment_point = attachment_point        # 첨부점
        
        self.matched_arrows = []
    
    def __repr__(self):
        return f"{self.entity_type}['{self.content}' at {self.position}, color={self.color}, style={self.style}]"


class ArrowLeader:
    """지시화살표선"""
    def __init__(self, arrow, leader_position, line_chain=None):
        self.arrow = arrow
        self.leader_position = leader_position
        self.line_chain = line_chain or [arrow.shaft]
        self.matched_text = None
        self.matched_boundaries = []
        self.id = None
    
    def __repr__(self):
        return f"ArrowLeader[{self.id}, text={self.matched_text.content if self.matched_text else 'None'}]"


class LeaderEntity:
    """LEADER 엔티티 (DXF의 LEADER)"""
    def __init__(self, handle, layer, vertices, has_arrowhead=True, color=None, linetype=None):
        self.handle = handle
        self.layer = layer
        self.vertices = vertices  # 꼭지점 리스트 [Point, Point, ...]
        self.has_arrowhead = has_arrowhead
        self.color = color
        self.linetype = linetype
        self.matched_text = None
        self.id = None
    
    def get_arrow_point(self):
        """화살표 끝점 (첫 번째 꼭지점)"""
        return self.vertices[0] if self.vertices else None
    
    def get_text_point(self):
        """텍스트 연결점 (마지막 꼭지점)"""
        return self.vertices[-1] if self.vertices else None
    
    def __repr__(self):
        return f"Leader[{self.id}, vertices={len(self.vertices)}, layer={self.layer}]"


class PolylineEntity:
    """POLYLINE 또는 LWPOLYLINE 엔티티"""
    def __init__(self, handle, layer, vertices, is_closed=False, entity_type='POLYLINE',
                 color=None, lineweight=None, linetype=None):
        self.handle = handle
        self.layer = layer
        self.vertices = vertices  # 꼭지점 리스트 [Point, Point, ...]
        self.is_closed = is_closed
        self.entity_type = entity_type  # 'POLYLINE' or 'LWPOLYLINE'
        self.color = color
        self.lineweight = lineweight
        self.linetype = linetype
        self.id = None
    
    def get_segment_count(self):
        """세그먼트 개수"""
        if len(self.vertices) < 2:
            return 0
        count = len(self.vertices) - 1
        if self.is_closed:
            count += 1
        return count
    
    def get_total_length(self):
        """전체 길이"""
        if len(self.vertices) < 2:
            return 0.0
        
        total = 0.0
        for i in range(len(self.vertices) - 1):
            total += distance(self.vertices[i], self.vertices[i + 1])
        
        # 닫힌 폴리라인이면 마지막과 첫 점 연결
        if self.is_closed:
            total += distance(self.vertices[-1], self.vertices[0])
        
        return total
    
    def __repr__(self):
        return f"{self.entity_type}[{self.id}, vertices={len(self.vertices)}, closed={self.is_closed}]"


# ============================================================================
# 유틸리티 함수 (Utility Functions)
# ============================================================================

def length(line):
    """선분의 길이"""
    dx = line.end_point.x - line.start_point.x
    dy = line.end_point.y - line.start_point.y
    return math.sqrt(dx*dx + dy*dy)


def distance(point1, point2):
    """두 점 사이의 거리"""
    dx = point2.x - point1.x
    dy = point2.y - point1.y
    return math.sqrt(dx*dx + dy*dy)


def direction_vector(line):
    """선분의 방향 벡터"""
    return (line.end_point.x - line.start_point.x,
            line.end_point.y - line.start_point.y)


def dot_product(v1, v2):
    """벡터 내적"""
    return v1[0]*v2[0] + v1[1]*v2[1]


def angle_between(line1, line2):
    """
    두 선분 사이의 각도 계산 (도 단위)
    Returns: 0° ~ 180°
    """
    v1 = direction_vector(line1)
    v2 = direction_vector(line2)
    
    dot = dot_product(v1, v2)
    mag1 = math.sqrt(v1[0]**2 + v1[1]**2)
    mag2 = math.sqrt(v2[0]**2 + v2[1]**2)
    
    if mag1 == 0 or mag2 == 0:
        return 0
    
    cos_angle = dot / (mag1 * mag2)
    cos_angle = max(-1.0, min(1.0, cos_angle))
    
    angle_rad = math.acos(cos_angle)
    angle_deg = math.degrees(angle_rad)
    
    return angle_deg


def are_lines_parallel(line1, line2, angle_threshold=5.0):
    """
    두 선분이 평행한지 판단
    
    Args:
        line1, line2: 비교할 선분
        angle_threshold: 평행 판정 각도 임계값 (도)
    
    Returns:
        bool: 평행이면 True
    """
    angle = angle_between(line1, line2)
    # 각도가 0도 근처 또는 180도 근처면 평행
    return angle < angle_threshold or angle > (180 - angle_threshold)


def get_leader_position(arrow_line, arrow_location):
    """지시화살표선이 가리키는 위치"""
    if arrow_location == 'end':
        return arrow_line.start_point
    elif arrow_location == 'start':
        return arrow_line.end_point
    elif arrow_location == 'both':
        mid_x = (arrow_line.start_point.x + arrow_line.end_point.x) / 2
        mid_y = (arrow_line.start_point.y + arrow_line.end_point.y) / 2
        return Point(mid_x, mid_y)


# ============================================================================
# DXF 파싱 함수 (DXF Parsing)
# ============================================================================

def load_dxf_file(filename):
    """DXF 파일 로드"""
    try:
        doc = ezdxf.readfile(filename)
        print(f"✓ DXF 파일 로드 성공: {filename}")
        print(f"  DXF 버전: {doc.dxfversion}")
        return doc
    except IOError:
        print(f"✗ 파일을 찾을 수 없습니다: {filename}")
        return None
    except ezdxf.DXFStructureError:
        print(f"✗ 잘못된 DXF 파일입니다: {filename}")
        return None


def extract_layers(doc):
    """레이어 정보 추출"""
    layers = {}
    msp = doc.modelspace()
    
    for entity in msp:
        layer_name = entity.dxf.layer
        if layer_name not in layers:
            layers[layer_name] = {
                'entity_count': 0,
                'entity_types': set()
            }
        layers[layer_name]['entity_count'] += 1
        layers[layer_name]['entity_types'].add(entity.dxftype())
    
    return layers


def classify_entities(doc):
    """엔티티 분류"""
    msp = doc.modelspace()
    entities = defaultdict(list)
    
    for entity in msp:
        entity_type = entity.dxftype()
        entities[entity_type].append(entity)
    
    return entities


def extract_lines(entities):
    """LINE 엔티티 추출 (색상, 두께, 선 종류 포함)"""
    lines = []
    for idx, entity in enumerate(entities.get('LINE', [])):
        start = entity.dxf.start
        end = entity.dxf.end
        
        # 색상 정보 추출 (기본값: None)
        color = getattr(entity.dxf, 'color', None)
        
        # 선 두께 정보 추출 (기본값: None)
        lineweight = getattr(entity.dxf, 'lineweight', None)
        
        # 선 종류 정보 추출 (기본값: None)
        linetype = getattr(entity.dxf, 'linetype', None)
        
        line = Line(
            Point(start[0], start[1]),
            Point(end[0], end[1]),
            handle=entity.dxf.handle,
            layer=entity.dxf.layer,
            color=color,
            lineweight=lineweight,
            linetype=linetype,
            line_id=f"L{idx:04d}"  # 라인 ID 부여 (L0000, L0001, ...)
        )
        lines.append(line)
    return lines


def extract_texts(entities):
    """TEXT 및 MTEXT 엔티티 추출 (색상, 폰트, 크기 등 모든 속성 포함)"""
    texts = []
    
    # TEXT
    for entity in entities.get('TEXT', []):
        text = TextEntity(
            handle=entity.dxf.handle,
            content=entity.dxf.text,
            position=Point(entity.dxf.insert[0], entity.dxf.insert[1]),
            layer=entity.dxf.layer,
            entity_type='TEXT',
            # 공통 속성
            color=getattr(entity.dxf, 'color', None),
            style=getattr(entity.dxf, 'style', None),
            rotation=getattr(entity.dxf, 'rotation', None),
            # TEXT 전용 속성
            height=getattr(entity.dxf, 'height', None),
            width=getattr(entity.dxf, 'width', None),
            halign=getattr(entity.dxf, 'halign', None),
            valign=getattr(entity.dxf, 'valign', None)
        )
        texts.append(text)
    
    # MTEXT
    for entity in entities.get('MTEXT', []):
        text = TextEntity(
            handle=entity.dxf.handle,
            content=entity.text,
            position=Point(entity.dxf.insert[0], entity.dxf.insert[1]),
            layer=entity.dxf.layer,
            entity_type='MTEXT',
            # 공통 속성
            color=getattr(entity.dxf, 'color', None),
            style=getattr(entity.dxf, 'style', None),
            rotation=getattr(entity.dxf, 'rotation', None),
            # MTEXT 전용 속성
            char_height=getattr(entity.dxf, 'char_height', None),
            width=getattr(entity.dxf, 'width', None),
            line_spacing_factor=getattr(entity.dxf, 'line_spacing_factor', None),
            attachment_point=getattr(entity.dxf, 'attachment_point', None)
        )
        texts.append(text)
    
    return texts


def extract_leaders(entities):
    """LEADER 엔티티 추출"""
    leaders = []
    
    for idx, entity in enumerate(entities.get('LEADER', [])):
        # 꼭지점 추출
        vertices = []
        for vertex in entity.vertices:
            vertices.append(Point(vertex[0], vertex[1]))
        
        # 화살촉 여부
        has_arrowhead = getattr(entity.dxf, 'has_arrowhead', True)
        
        # 색상 및 선 종류
        color = getattr(entity.dxf, 'color', None)
        linetype = getattr(entity.dxf, 'linetype', None)
        
        leader = LeaderEntity(
            handle=entity.dxf.handle,
            layer=entity.dxf.layer,
            vertices=vertices,
            has_arrowhead=has_arrowhead,
            color=color,
            linetype=linetype
        )
        leader.id = f"LD{idx:03d}"
        leaders.append(leader)
    
    return leaders


def extract_polylines(entities):
    """POLYLINE 및 LWPOLYLINE 엔티티 추출"""
    polylines = []
    idx = 0
    
    # POLYLINE 추출
    for entity in entities.get('POLYLINE', []):
        # 꼭지점 추출
        vertices = []
        for vertex in entity:
            location = vertex.dxf.location
            vertices.append(Point(location[0], location[1]))
        
        # 닫힌 폴리라인 여부
        is_closed = entity.is_closed
        
        # 색상, 두께, 선 종류
        color = getattr(entity.dxf, 'color', None)
        lineweight = getattr(entity.dxf, 'lineweight', None)
        linetype = getattr(entity.dxf, 'linetype', None)
        
        polyline = PolylineEntity(
            handle=entity.dxf.handle,
            layer=entity.dxf.layer,
            vertices=vertices,
            is_closed=is_closed,
            entity_type='POLYLINE',
            color=color,
            lineweight=lineweight,
            linetype=linetype
        )
        polyline.id = f"PL{idx:04d}"
        polylines.append(polyline)
        idx += 1
    
    # LWPOLYLINE 추출
    for entity in entities.get('LWPOLYLINE', []):
        # 꼭지점 추출
        vertices = []
        for point in entity.get_points():
            vertices.append(Point(point[0], point[1]))
        
        # 닫힌 폴리라인 여부
        is_closed = entity.closed
        
        # 색상, 두께, 선 종류
        color = getattr(entity.dxf, 'color', None)
        lineweight = getattr(entity.dxf, 'const_width', None)
        linetype = getattr(entity.dxf, 'linetype', None)
        
        polyline = PolylineEntity(
            handle=entity.dxf.handle,
            layer=entity.dxf.layer,
            vertices=vertices,
            is_closed=is_closed,
            entity_type='LWPOLYLINE',
            color=color,
            lineweight=lineweight,
            linetype=linetype
        )
        polyline.id = f"PL{idx:04d}"
        polylines.append(polyline)
        idx += 1
    
    return polylines


# ============================================================================
# 화살표 탐지 (Arrow Detection)
# ============================================================================

def check_symmetrical_lines(shaft_line, meeting_line_indices, lines, line_lengths, 
                           used_barbs, arrow_config):
    """
    주축선의 한 끝점에서 만나는 선분들 중 대칭선 조건을 만족하는 쌍 찾기
    
    Args:
        shaft_line: 주축선
        meeting_line_indices: 만나는 선분들의 인덱스 리스트 [(line_idx, 'start'|'end'), ...]
        lines: 전체 선분 리스트
        line_lengths: 전체 선분 길이 리스트
        used_barbs: 이미 대칭선으로 사용된 선분 인덱스 집합 (set)
        arrow_config: 화살표 설정
    
    Returns:
        tuple: (barb1_idx, barb2_idx) 또는 None
    """
    barb_length_diff_max = arrow_config['barb_length_diff_max']
    arrow_angle_max = arrow_config['arrow_angle_max']
    barb_angle_diff_max = arrow_config['barb_angle_diff_max']
    
    # 2개 이상이어야 대칭선 검사 가능
    if len(meeting_line_indices) < 2:
        return None
    
    # 모든 2개 조합 검사
    for idx1 in range(len(meeting_line_indices)):
        for idx2 in range(idx1 + 1, len(meeting_line_indices)):
            line_j_idx, _ = meeting_line_indices[idx1]
            line_k_idx, _ = meeting_line_indices[idx2]
            
            # 이미 대칭선으로 사용된 선분은 제외
            if line_j_idx in used_barbs or line_k_idx in used_barbs:
                continue
            
            line_j = lines[line_j_idx]
            line_k = lines[line_k_idx]
            
            # 조건 1: 두 대칭선의 길이 차이
            barb_j_length = line_lengths[line_j_idx]
            barb_k_length = line_lengths[line_k_idx]
            length_diff = abs(barb_j_length - barb_k_length)
            
            if length_diff > barb_length_diff_max:
                continue
            
            # 조건 2: 주축선과의 각도
            angle_j = angle_between(shaft_line, line_j)
            angle_k = angle_between(shaft_line, line_k)
            
            if angle_j > arrow_angle_max or angle_k > arrow_angle_max:
                continue
            
            # 조건 3: 두 대칭선의 각도 차이
            angle_diff = abs(angle_j - angle_k)
            
            if angle_diff > barb_angle_diff_max:
                continue
            
            # 대칭선 조건 만족!
            return (line_j_idx, line_k_idx)
    
    return None


def detect_arrows_in_drawing(lines, config):
    """
    도면에서 모든 화살표 탐지 (최적화된 단계별 알고리즘)
    
    화살표 = 주축선 1개 + 대칭선 2개
    - 3개 선분의 시작점 또는 끝점이 한 점에서 만남
    - 대칭선은 주축선보다 짧음
    - 두 대칭선의 길이가 비슷함
    """
    
    arrows = []
    arrow_config = config['ARROW_DETECTION']
    tip_tolerance = arrow_config['tip_point_tolerance']
    
    # 이미 대칭선으로 사용된 선분 인덱스 저장
    used_barbs = set()
    
    print(f"\n화살표 탐지 중...")
    print(f"  전체 선분: {len(lines)}개")
    
    # ========================================================================
    # 1차 프로세스: 모든 직선의 길이 계산
    # ========================================================================
    print(f"\n[1차 프로세스] 선분 길이 계산 중...")
    line_lengths = []
    for line in lines:
        line_lengths.append(length(line))
    print(f"✓ 완료: {len(line_lengths)}개 선분 길이 계산")
    
    # ========================================================================
    # 2차 프로세스: 각 선분의 시작점/끝점에서 만나는 더 짧은 선분 찾기
    # ========================================================================
    print(f"\n[2차 프로세스] 만나는 선분 검색 중...")
    
    # 각 선분의 시작점/끝점에서 만나는 선분 정보 저장
    meeting_lines = []
    for i in range(len(lines)):
        meeting_lines.append({'start': [], 'end': []})
    
    parallel_skipped = 0  # 평행선 제외 카운트
    
    for i, line_i in enumerate(lines):
        if (i + 1) % 100 == 0:
            print(f"  진행: {i+1}/{len(lines)} 선분 처리 중...")
        
        line_i_length = line_lengths[i]
        
        for j, line_j in enumerate(lines):
            if i == j:
                continue
            
            line_j_length = line_lengths[j]
            
            # line_j가 line_i보다 짧은 경우만 검사
            if line_j_length >= line_i_length:
                continue
            
            # 평행선 체크 - 평행이면 화살표 불가능
            if are_lines_parallel(line_i, line_j):
                parallel_skipped += 1
                continue
            
            # 4가지 점 조합의 거리 계산
            distances = [
                (distance(line_i.start_point, line_j.start_point), 'i_start', 'j_start'),
                (distance(line_i.start_point, line_j.end_point), 'i_start', 'j_end'),
                (distance(line_i.end_point, line_j.start_point), 'i_end', 'j_start'),
                (distance(line_i.end_point, line_j.end_point), 'i_end', 'j_end')
            ]
            
            # 가장 가까운 거리 찾기
            min_dist, i_point, j_point = min(distances, key=lambda x: x[0])
            
            # 가장 가까운 거리가 허용 오차 이내일 때만 저장
            if min_dist <= tip_tolerance:
                # line_i의 어느 점인지에 따라 저장
                if i_point == 'i_start':
                    meeting_lines[i]['start'].append((j, j_point.split('_')[1]))  # 'start' or 'end'
                else:  # i_point == 'i_end'
                    meeting_lines[i]['end'].append((j, j_point.split('_')[1]))  # 'start' or 'end'
    
    # 2차 프로세스 결과 출력
    count_start_2 = sum(1 for ml in meeting_lines if len(ml['start']) >= 2)
    count_end_2 = sum(1 for ml in meeting_lines if len(ml['end']) >= 2)
    total_endpoints_with_2_meetings = count_start_2 + count_end_2
    
    print(f"✓ 완료")
    print(f"  평행선 제외: {parallel_skipped}개 조합")
    print(f"  시작점에서 2개 이상 만나는 선분: {count_start_2}개")
    print(f"  끝점에서 2개 이상 만나는 선분: {count_end_2}개")
    print(f"  총 2개 이상 만나는 끝점 수: {total_endpoints_with_2_meetings}개")
    
    # ========================================================================
    # 3차 프로세스: 만나는 선분들이 대칭선 조건을 만족하는지 검사
    # ========================================================================
    print(f"\n[3차 프로세스] 화살표 패턴 검증 중...")
    
    arrow_count = 0
    
    for i, line_i in enumerate(lines):
        if (i + 1) % 100 == 0:
            print(f"  진행: {i+1}/{len(lines)} 선분 검증 중... (발견: {arrow_count}개)")
        
        # 시작점 검사
        if len(meeting_lines[i]['start']) >= 2:
            result = check_symmetrical_lines(
                shaft_line=line_i,
                meeting_line_indices=meeting_lines[i]['start'],
                lines=lines,
                line_lengths=line_lengths,
                used_barbs=used_barbs,
                arrow_config=arrow_config
            )
            
            if result:
                barb1_idx, barb2_idx = result
                
                # 화살표 생성
                arrow = Arrow(
                    shaft=line_i,
                    left_barb=lines[barb1_idx],
                    right_barb=lines[barb2_idx],
                    tip_point=line_i.start_point,
                    direction='start'
                )
                arrows.append(arrow)
                arrow_count += 1
                
                # 대칭선으로 사용됨 표시
                used_barbs.add(barb1_idx)
                used_barbs.add(barb2_idx)
        
        # 끝점 검사
        if len(meeting_lines[i]['end']) >= 2:
            result = check_symmetrical_lines(
                shaft_line=line_i,
                meeting_line_indices=meeting_lines[i]['end'],
                lines=lines,
                line_lengths=line_lengths,
                used_barbs=used_barbs,
                arrow_config=arrow_config
            )
            
            if result:
                barb1_idx, barb2_idx = result
                
                # 화살표 생성
                arrow = Arrow(
                    shaft=line_i,
                    left_barb=lines[barb1_idx],
                    right_barb=lines[barb2_idx],
                    tip_point=line_i.end_point,
                    direction='end'
                )
                arrows.append(arrow)
                arrow_count += 1
                
                # 대칭선으로 사용됨 표시
                used_barbs.add(barb1_idx)
                used_barbs.add(barb2_idx)
    
    # 3차 프로세스 결과 출력
    print(f"✓ 완료")
    print(f"  화살표로 판정된 선분: {arrow_count}개")
    print(f"  대칭선으로 사용된 선분: {len(used_barbs)}개")
    
    # ID 부여
    for i, arrow in enumerate(arrows, 1):
        arrow.id = f"ARW{i:03d}"
    
    print(f"\n✓ 화살표 탐지 완료: {len(arrows)}개 발견")
    
    return arrows


# ============================================================================
# 지시화살표선 생성 (Arrow Leader Creation)
# ============================================================================

def create_arrow_leaders(arrows):
    """화살표로부터 지시화살표선 생성"""
    
    arrow_leaders = []
    
    for arrow in arrows:
        # 지시 위치 결정
        leader_pos = get_leader_position(arrow.shaft, arrow.direction)
        
        arrow_leader = ArrowLeader(
            arrow=arrow,
            leader_position=leader_pos,
            line_chain=[arrow.shaft]
        )
        
        arrow_leaders.append(arrow_leader)
    
    # ID 부여
    for i, leader in enumerate(arrow_leaders, 1):
        leader.id = f"A{i:03d}"
    
    return arrow_leaders


# ============================================================================
# 텍스트 매칭 (Text Matching)
# ============================================================================

def match_texts_to_arrows(arrow_leaders, texts, config):
    """지시화살표선과 텍스트 매칭"""
    
    max_distance = config['LEADER_ARROW_MATCHING']['max_distance']
    
    print(f"\n텍스트 매칭 중...")
    
    for leader in arrow_leaders:
        min_dist = float('inf')
        closest_text = None
        
        for text in texts:
            dist = distance(leader.leader_position, text.position)
            
            if dist < max_distance and dist < min_dist:
                min_dist = dist
                closest_text = text
        
        if closest_text:
            leader.matched_text = closest_text
            closest_text.matched_arrows.append(leader)
    
    matched_count = sum(1 for leader in arrow_leaders if leader.matched_text is not None)
    print(f"✓ 텍스트 매칭 완료: {matched_count}/{len(arrow_leaders)}개 매칭")
    
    return arrow_leaders


# ============================================================================
# 지시경계선 탐지 (Boundary Line Detection)
# ============================================================================

def detect_boundary_lines(arrow_leaders, lines, config):
    """지시경계선 탐지"""
    
    boundary_config = config['LEADER_BOUNDARY_MATCHING']
    max_dist = boundary_config['max_distance_to_arrow']
    angle_min = boundary_config['perpendicular_angle_min']
    angle_max = boundary_config['perpendicular_angle_max']
    
    print(f"\n지시경계선 탐지 중...")
    
    # 화살표가 사용한 선분들 제외
    arrow_lines = set()
    for leader in arrow_leaders:
        arrow_lines.add(leader.arrow.shaft)
        arrow_lines.add(leader.arrow.left_barb)
        arrow_lines.add(leader.arrow.right_barb)
    
    boundary_lines = []
    
    for leader in arrow_leaders:
        arrow_tip = leader.arrow.tip_point
        arrow_shaft = leader.arrow.shaft
        
        for line in lines:
            # 화살표 구성 선분 제외
            if line in arrow_lines:
                continue
            
            # 조건 1: 화살표 위치와의 거리
            dist_to_start = distance(arrow_tip, line.start_point)
            dist_to_end = distance(arrow_tip, line.end_point)
            min_dist_to_line = min(dist_to_start, dist_to_end)
            
            if min_dist_to_line > max_dist:
                continue
            
            # 조건 2: 화살표 직선과의 각도 (직각)
            angle = angle_between(arrow_shaft, line)
            
            if angle_min <= angle <= angle_max:
                leader.matched_boundaries.append(line)
                boundary_lines.append(line)
    
    print(f"✓ 지시경계선 탐지 완료: {len(boundary_lines)}개 발견")
    
    return boundary_lines


# ============================================================================
# 보고서 생성 (Report Generation)
# ============================================================================

def generate_report(doc, layers, entities, texts, arrows, arrow_leaders, boundary_lines, 
                   leaders, polylines, filename):
    """분석 보고서 생성"""
    
    with open(filename, 'w', encoding='utf-8') as f:
        # 헤더
        f.write("=" * 80 + "\n")
        f.write(" " * 25 + "DXF 파일 분석 보고서\n")
        f.write("=" * 80 + "\n\n")
        
        # 1. 파일 정보
        f.write("[1. 파일 정보]\n")
        f.write("-" * 80 + "\n")
        f.write(f"파일명         : {INPUT_FILE}\n")
        f.write(f"DXF 버전       : {doc.dxfversion}\n")
        f.write(f"분석 일시      : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"화살표 탐지    : {'활성화' if ON_DETECT_EX_LEADERS else '비활성화'}\n")
        f.write("\n")
        
        # 2. 레이어 구조
        f.write("[2. 레이어 구조]\n")
        f.write("-" * 80 + "\n")
        f.write(f"{'레이어명':<20} | {'엔티티 수':>10} | 주요 엔티티 유형\n")
        f.write("-" * 80 + "\n")
        for layer_name, info in sorted(layers.items()):
            entity_types = ', '.join(sorted(info['entity_types']))[:40]
            f.write(f"{layer_name:<20} | {info['entity_count']:>10} | {entity_types}\n")
        f.write(f"\n총 레이어 수: {len(layers)}개\n\n")
        
        # 3. 엔티티 분류 통계
        f.write("[3. 엔티티 분류 통계]\n")
        f.write("-" * 80 + "\n")
        f.write(f"{'엔티티 유형':<20} | {'총 개수':>10}\n")
        f.write("-" * 80 + "\n")
        for entity_type, entity_list in sorted(entities.items()):
            f.write(f"{entity_type:<20} | {len(entity_list):>10}\n")
        f.write("\n")

        # 4. 화살표 탐지 결과
        f.write("[4. 화살표 탐지 결과]\n")
        f.write("-" * 80 + "\n")
        f.write(f"총 탐지된 화살표: {len(arrows)}개\n\n")

        for arrow in arrows[:10]:  # 처음 10개만 표시
            f.write(f"ID: {arrow.id}\n")
            f.write(f"  주축선        : [{arrow.shaft.id}] {arrow.shaft.start_point} → {arrow.shaft.end_point}\n")
            f.write(f"  왼쪽 화살촉 : [{arrow.left_barb.id}] {arrow.left_barb.start_point} → {arrow.left_barb.end_point}\n")
            f.write(f"  오른쪽 화살촉: [{arrow.right_barb.id}] {arrow.right_barb.start_point} → {arrow.right_barb.end_point}\n")
            f.write(f"  화살표 방향 : {arrow.direction}\n")
            f.write("\n")
        
        if len(arrows) > 10:
            f.write(f"... 외 {len(arrows) - 10}개\n\n")
        
        # 5. 치수/주석 상세 분석
        f.write("[5. 치수/주석 상세 분석]\n")
        f.write("-" * 80 + "\n")
        
        # 5.1 텍스트 엔티티
        f.write(f"\n5.1 텍스트 엔티티 ({len(texts)}개)\n")
        f.write("-" * 80 + "\n")
        for text in texts[:20]:  # 처음 20개만
            f.write(f"\nID: {text.handle}\n")
            f.write(f"  유형   : {text.entity_type}\n")
            f.write(f"  내용   : \"{text.content}\"\n")
            f.write(f"  위치   : {text.position}\n")
            f.write(f"  레이어 : {text.layer}\n")
            if text.matched_arrows:
                arrow_ids = ', '.join([a.id for a in text.matched_arrows])
                f.write(f"  매칭된 화살표: {arrow_ids}\n")
            else:
                f.write(f"  매칭된 화살표: 없음 ⚠️\n")
        
        if len(texts) > 20:
            f.write(f"\n... 외 {len(texts) - 20}개\n")

        # 5.2 지시화살표선
        f.write(f"\n\n5.2 지시화살표선 ({len(arrow_leaders)}개)\n")
        f.write("-" * 80 + "\n")
        for leader in arrow_leaders[:20]:  # 처음 20개만
            f.write(f"\nID: {leader.id}\n")
            f.write(f"  화살표 ID    : {leader.arrow.id}\n")
            f.write(f"  지시 위치    : {leader.leader_position}\n")
            f.write(f"  화살표 방향  : {leader.arrow.direction}\n")
            if leader.matched_text:
                f.write(f"  매칭된 텍스트: \"{leader.matched_text.content}\"\n")
            else:
                f.write(f"  매칭된 텍스트: 없음 ⚠️\n")
            if leader.matched_boundaries:
                f.write(f"  매칭된 경계선 : {len(leader.matched_boundaries)}개\n")
        
        if len(arrow_leaders) > 20:
            f.write(f"\n... 외 {len(arrow_leaders) - 20}개\n")
        
        # 5.3 LEADER 엔티티
        f.write(f"\n\n5.3 LEADER 엔티티 ({len(leaders)}개)\n")
        f.write("-" * 80 + "\n")
        for leader in leaders[:10]:  # 처음 10개만
            f.write(f"\nID: {leader.id}\n")
            f.write(f"  레이어        : {leader.layer}\n")
            f.write(f"  화살촉 여부   : {leader.has_arrowhead}\n")
            f.write(f"  색상          : {leader.color}\n")
            f.write(f"  선 종류       : {leader.linetype}\n")
            if leader.matched_text:
                f.write(f"  매칭된 텍스트 : \"{leader.matched_text.content}\"\n")
            else:
                f.write(f"  매칭된 텍스트 : 없음\n")
            
            # 꼭지점 정보
            f.write(f"  꼭지점 개수   : {len(leader.vertices)}개\n")
            if leader.vertices:
                f.write(f"  꼭지점 목록   :\n")
                for idx, vertex in enumerate(leader.vertices[:20]):  # 최대 20개
                    f.write(f"    [{idx}] {vertex}\n")
                if len(leader.vertices) > 20:
                    f.write(f"    ... 외 {len(leader.vertices) - 20}개\n")
        
        if len(leaders) > 10:
            f.write(f"\n... 외 {len(leaders) - 10}개\n")
        
        # 5.4 POLYLINE 엔티티
        f.write(f"\n\n5.4 POLYLINE/LWPOLYLINE 엔티티 ({len(polylines)}개)\n")
        f.write("-" * 80 + "\n")
        for polyline in polylines[:10]:  # 처음 10개만
            f.write(f"\nID: {polyline.id}\n")
            f.write(f"  레이어        : {polyline.layer}\n")
            f.write(f"  닫힌 여부     : {polyline.is_closed}\n")
            f.write(f"  유형          : {polyline.entity_type}\n")
            f.write(f"  색상          : {polyline.color}\n")
            f.write(f"  선 두께       : {polyline.lineweight}\n")
            f.write(f"  선 종류       : {polyline.linetype}\n")
            
            # 꼭지점 정보
            f.write(f"  꼭지점 개수   : {len(polyline.vertices)}개\n")
            if polyline.vertices:
                f.write(f"  꼭지점 목록   :\n")
                for idx, vertex in enumerate(polyline.vertices[:20]):  # 최대 20개
                    f.write(f"    [{idx}] {vertex}\n")
                if len(polyline.vertices) > 20:
                    f.write(f"    ... 외 {len(polyline.vertices) - 20}개\n")
        
        if len(polylines) > 10:
            f.write(f"\n... 외 {len(polylines) - 10}개\n")
        
        # 6. 검출된 문제점
        f.write("\n\n[6. 검출된 문제점]\n")
        f.write("-" * 80 + "\n")
        
        unmatched_texts = [t for t in texts if not t.matched_arrows]
        unmatched_leaders = [l for l in arrow_leaders if l.matched_text is None]
        leaders_without_boundaries = [l for l in arrow_leaders if not l.matched_boundaries]
        
        f.write(f"⚠️ 매칭되지 않은 텍스트: {len(unmatched_texts)}개\n")
        if unmatched_texts:
            for text in unmatched_texts[:5]:
                f.write(f"   - {text.handle}: \"{text.content}\" at {text.position}\n")
        
        f.write(f"\n⚠️ 텍스트가 없는 지시화살표선: {len(unmatched_leaders)}개\n")
        if unmatched_leaders:
            for leader in unmatched_leaders[:5]:
                f.write(f"   - {leader.id} at {leader.leader_position}\n")
        
        f.write(f"\n⚠️ 지시경계선이 없는 지시화살표선: {len(leaders_without_boundaries)}개\n")
        
        # 7. 통계 요약
        f.write("\n\n[7. 통계 요약]\n")
        f.write("-" * 80 + "\n")
        f.write(f"총 치수/주석 엔티티    : {len(texts)}개\n")
        f.write(f"탐지된 화살표          : {len(arrows)}개\n")
        f.write(f"탐지된 지시화살표선      : {len(arrow_leaders)}개\n")
        f.write(f"탐지된 지시경계선        : {len(boundary_lines)}개\n")
        f.write(f"LEADER 엔티티          : {len(leaders)}개\n")
        f.write(f"POLYLINE 엔티티        : {len(polylines)}개\n")
        
        matched_count = len([l for l in arrow_leaders if l.matched_text])
        if len(arrow_leaders) > 0:
            match_rate = (matched_count / len(arrow_leaders)) * 100
            f.write(f"매칭 성공률              : {match_rate:.1f}%\n")
        
        f.write(f"처리된 레이어          : {len(layers)}개\n")
        
        # 푸터
        f.write("\n" + "=" * 80 + "\n")
        f.write(" " * 30 + "분석 보고서 끝\n")
        f.write("=" * 80 + "\n")
    
    print(f"\n✓ 보고서 생성 완료: {filename}")


# ============================================================================
# 메인 함수 (Main)
# ============================================================================

def main():
    """메인 실행 함수"""

    # 변수 초기화 (ON_DETECT_EX_LEADERS가 True일 때 사용)
    arrows = []
    arrow_leaders = []
    boundary_lines = []

    print("=" * 80)
    print(" " * 25 + "CAD-Work: DXF 파일 분석")
    print("=" * 80)
    print(f"\n입력 파일: {INPUT_FILE}")
    print(f"출력 파일: {OUTPUT_REPORT}")
    
    # 1. DXF 파일 로드
    print("\n" + "=" * 80)
    print("1단계: DXF 파일 로드")
    print("=" * 80)
    doc = load_dxf_file(INPUT_FILE)
    if doc is None:
        return
    
    # 2. 레이어 구조 분석
    print("\n" + "=" * 80)
    print("2단계: 레이어 구조 분석")
    print("=" * 80)
    layers = extract_layers(doc)
    print(f"✓ 레이어 분석 완료: {len(layers)}개 레이어 발견")
    
    # 3. 엔티티 분류
    print("\n" + "=" * 80)
    print("3단계: 엔티티 분류")
    print("=" * 80)
    entities = classify_entities(doc)
    print(f"✓ 엔티티 분류 완료: {len(entities)}개 유형")
    for entity_type, entity_list in sorted(entities.items()):
        print(f"  {entity_type}: {len(entity_list)}개")
    
    # 4. LINE 및 TEXT 추출
    print("\n" + "=" * 80)
    print("4단계: LINE, TEXT, LEADER, POLYLINE 추출")
    print("=" * 80)
    lines = extract_lines(entities)
    texts = extract_texts(entities)
    leaders = extract_leaders(entities)
    polylines = extract_polylines(entities)
    print(f"✓ LINE 추출: {len(lines)}개")
    print(f"✓ TEXT/MTEXT 추출: {len(texts)}개")
    print(f"✓ LEADER 추출: {len(leaders)}개")
    print(f"✓ POLYLINE/LWPOLYLINE 추출: {len(polylines)}개")

    if ON_DETECT_EX_LEADERS:
        # 지시선이 아닌 직선이지만, 지시선의 역할을 하는 선들을 찾는다

        # 51. 화살표 탐지
        # -> LINE 렌더 (들)에 화살표 형태인지를 확인
        # -> 좀 더 상세하게는, 다른 직선 2개의 대칭선의 역할을 해서, 3개의 직선이 꼭지점이 같은 지를 검사
        print("\n" + "=" * 80)
        print("51단계: 화살표 탐지")
        print("=" * 80)
        arrows = detect_arrows_in_drawing(lines, CONFIG)
    
        # 52. 지시화살표선 생성
        print("\n" + "=" * 80)
        print("52단계: 지시화살표선 생성")
        print("=" * 80)
        arrow_leaders = create_arrow_leaders(arrows)
        print(f"✓ 지시화살표선 생성: {len(arrow_leaders)}개")

        # 53. 지시경계선 탐지
        print("\n" + "=" * 80)
        print("53단계: 지시경계선 탐지")
        print("=" * 80)
        boundary_lines = detect_boundary_lines(arrow_leaders, lines, CONFIG)

        # 54. 텍스트 매칭
        print("\n" + "=" * 80)
        print("54단계: 텍스트 매칭")
        print("=" * 80)
        arrow_leaders = match_texts_to_arrows(arrow_leaders, texts, CONFIG)

    # 9. 보고서 생성
    print("\n" + "=" * 80)
    print("9단계: 보고서 생성")
    print("=" * 80)
    generate_report(doc, layers, entities, texts, arrows, arrow_leaders, 
                   boundary_lines, leaders, polylines, OUTPUT_REPORT)
    
    # 완료
    print("\n" + "=" * 80)
    print(" " * 30 + "분석 완료!")
    print("=" * 80)


if __name__ == "__main__":
    main()