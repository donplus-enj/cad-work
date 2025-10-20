"""
chk_dimension.py
DXF 파일 분석 모듈 - 치수/주석 정보 추출 및 분석

CAD-Work 프로젝트
버전: 1.0
"""

import ezdxf
import math
from datetime import datetime
from collections import defaultdict
from itertools import combinations

from matplotlib import lines


# ============================================================================
# 설정 (Configuration)
# ============================================================================

# 파일 경로 설정 (직접 지정)
INPUT_FILE = "data\\gear-disk\\Gear Disk dxf File.dxf"  # 분석할 DXF 파일
OUTPUT_REPORT = "data\\gear-disk\\analysis_report.txt"  # 출력 보고서 파일명

# 화살표 탐지 설정
CONFIG = {
    'ARROW_DETECTION': {
        'arrow_length_min': 2.0,        # 화살촉 최소 길이 (mm)
        'arrow_length_max': 5.0,        # 화살촉 최대 길이 (mm)
        'arrow_angle_min': 15.0,        # 화살촉 최소 각도 (도)
        'arrow_angle_max': 45.0,        # 화살촉 최대 각도 (도)
        'tip_point_tolerance': 0.1,     # 끝점 일치 허용 오차 (mm)
        'check_symmetry': False,        # 대칭성 검사 여부
        'symmetry_tolerance': 5.0,      # 대칭 허용 오차 (도)
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
    def __init__(self, start, end, handle=None, layer=None):
        self.start_point = start if isinstance(start, Point) else Point(start[0], start[1])
        self.end_point = end if isinstance(end, Point) else Point(end[0], end[1])
        self.handle = handle
        self.layer = layer
    
    def __repr__(self):
        return f"Line[{self.start_point} → {self.end_point}]"


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
    def __init__(self, handle, content, position, layer, entity_type='TEXT'):
        self.handle = handle
        self.content = content
        self.position = position if isinstance(position, Point) else Point(position[0], position[1])
        self.layer = layer
        self.entity_type = entity_type
        self.matched_arrows = []
    
    def __repr__(self):
        return f"{self.entity_type}['{self.content}' at {self.position}]"


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


def lines_meet(line_A, line_B, tolerance):
    """두 선분이 만나는지 판정"""
    endpoints_A = [line_A.start_point, line_A.end_point]
    endpoints_B = [line_B.start_point, line_B.end_point]
    
    for point_A in endpoints_A:
        for point_B in endpoints_B:
            if distance(point_A, point_B) < tolerance:
                return True
    return False


def get_meeting_point(line_A, line_B, tolerance):
    """두 선분이 만나는 점 반환 (평균 좌표)"""
    endpoints_A = [line_A.start_point, line_A.end_point]
    endpoints_B = [line_B.start_point, line_B.end_point]
    
    for point_A in endpoints_A:
        for point_B in endpoints_B:
            if distance(point_A, point_B) < tolerance:
                avg_x = (point_A.x + point_B.x) / 2
                avg_y = (point_A.y + point_B.y) / 2
                return Point(avg_x, avg_y)
    return None


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
    """LINE 엔티티 추출"""
    lines = []
    for entity in entities.get('LINE', []):
        start = entity.dxf.start
        end = entity.dxf.end
        line = Line(
            Point(start[0], start[1]),
            Point(end[0], end[1]),
            handle=entity.dxf.handle,
            layer=entity.dxf.layer
        )
        lines.append(line)
    return lines


def extract_texts(entities):
    """TEXT 및 MTEXT 엔티티 추출"""
    texts = []
    
    # TEXT
    for entity in entities.get('TEXT', []):
        text = TextEntity(
            handle=entity.dxf.handle,
            content=entity.dxf.text,
            position=Point(entity.dxf.insert[0], entity.dxf.insert[1]),
            layer=entity.dxf.layer,
            entity_type='TEXT'
        )
        texts.append(text)
    
    # MTEXT
    for entity in entities.get('MTEXT', []):
        text = TextEntity(
            handle=entity.dxf.handle,
            content=entity.text,
            position=Point(entity.dxf.insert[0], entity.dxf.insert[1]),
            layer=entity.dxf.layer,
            entity_type='MTEXT'
        )
        texts.append(text)
    
    return texts


# ============================================================================
# 화살표 탐지 (Arrow Detection)
# ============================================================================

def is_arrow_pattern(shaft_line, barb1, barb2, config):
    """화살표 패턴 판정 (5가지 조건)"""
    
    # 조건 2: 화살촉 길이
    barb1_length = length(barb1)
    barb2_length = length(barb2)
    
    min_len = config['arrow_length_min']
    max_len = config['arrow_length_max']
    
    if not (min_len <= barb1_length <= max_len and
            min_len <= barb2_length <= max_len):
        return False
    
    # 조건 3: 화살촉 각도
    angle1 = angle_between(shaft_line, barb1)
    angle2 = angle_between(shaft_line, barb2)
    
    min_angle = config['arrow_angle_min']
    max_angle = config['arrow_angle_max']
    
    if not (min_angle <= angle1 <= max_angle and
            min_angle <= angle2 <= max_angle):
        return False
    
    # 조건 4: 대칭성 (선택)
    if config.get('check_symmetry', False):
        angle_diff = abs(angle1 - angle2)
        symmetry_tolerance = config.get('symmetry_tolerance', 5.0)
        
        if angle_diff > symmetry_tolerance:
            return False
    
    # 조건 5: 방향성
    shaft_direction = direction_vector(shaft_line)
    barb1_direction = direction_vector(barb1)
    barb2_direction = direction_vector(barb2)
    
    # 화살촉이 주축선 반대 방향을 향해야 함
    if not (dot_product(shaft_direction, barb1_direction) < 0 and
            dot_product(shaft_direction, barb2_direction) < 0):
        return False
    
    return True


def check_arrow_at_endpoint(shaft_line, tip_point, candidate_lines, config, reverse=False):
    """특정 점에서 화살표 패턴 확인"""
    
    # Step 1: tip_point 근처의 선분 찾기
    nearby_lines = []
    tolerance = config['tip_point_tolerance']
    
    for line in candidate_lines:
        if distance(line.start_point, tip_point) < tolerance:
            nearby_lines.append(line)
    
    # Step 2: 최소 2개의 선분 필요
    if len(nearby_lines) < 2:
        return None
    
    # Step 3: 가능한 모든 2개 조합 검사
    for barb1, barb2 in combinations(nearby_lines, 2):
        # 화살표 패턴 검사
        if is_arrow_pattern(shaft_line, barb1, barb2, config):
            return Arrow(
                shaft=shaft_line,
                left_barb=barb1,
                right_barb=barb2,
                tip_point=tip_point,
                direction='start' if reverse else 'end'
            )
    
    return None


def detect_arrows_in_drawing(lines, config):
    """도면에서 모든 화살표 탐지"""
    
    arrows = []
    arrow_config = config['ARROW_DETECTION']
    
    # Step 1: 선분을 길이 기준으로 분류
    long_lines = []
    short_lines = []

    for line in lines:

        line_length = length(line)

        if line_length > arrow_config['arrow_length_max']:
            long_lines.append(line)
        else:
            short_lines.append(line)

    print(f"\n화살표 탐지 중...")
    print(f"  주축선 후보: {len(long_lines)}개")
    print(f"  화살촉 후보: {len(short_lines)}개")
    
    # Step 2: 각 긴 선분의 양 끝점에서 화살표 검사
    for i, shaft in enumerate(long_lines):
        # 진행 상황 표시
        if (i + 1) % 50 == 0:
            print(f"  진행: {i+1}/{len(long_lines)}...")
        
        # 끝점에서 화살표 확인
        arrow = check_arrow_at_endpoint(
            shaft,
            shaft.end_point,
            short_lines,
            arrow_config,
            reverse=False
        )
        if arrow:
            arrows.append(arrow)
        
        # 시작점에서 화살표 확인
        arrow = check_arrow_at_endpoint(
            shaft,
            shaft.start_point,
            short_lines,
            arrow_config,
            reverse=True
        )
        if arrow:
            arrows.append(arrow)
    
    # ID 부여
    for i, arrow in enumerate(arrows, 1):
        arrow.id = f"ARW{i:03d}"
    
    print(f"✓ 화살표 탐지 완료: {len(arrows)}개 발견")
    
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

def generate_report(doc, layers, entities, texts, arrows, arrow_leaders, boundary_lines, filename):
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
            f.write(f"  주축선      : {arrow.shaft.start_point} → {arrow.shaft.end_point}\n")
            f.write(f"  왼쪽 화살촉 : {arrow.left_barb.start_point} → {arrow.left_barb.end_point}\n")
            f.write(f"  오른쪽 화살촉: {arrow.right_barb.start_point} → {arrow.right_barb.end_point}\n")
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
                f.write(f"  매칭된 경계선: {len(leader.matched_boundaries)}개\n")
        
        if len(arrow_leaders) > 20:
            f.write(f"\n... 외 {len(arrow_leaders) - 20}개\n")
        
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
        f.write(f"탐지된 지시화살표선    : {len(arrow_leaders)}개\n")
        f.write(f"탐지된 지시경계선      : {len(boundary_lines)}개\n")
        
        matched_count = len([l for l in arrow_leaders if l.matched_text])
        if len(arrow_leaders) > 0:
            match_rate = (matched_count / len(arrow_leaders)) * 100
            f.write(f"매칭 성공률            : {match_rate:.1f}%\n")
        
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
    print("4단계: LINE 및 TEXT 추출")
    print("=" * 80)
    lines = extract_lines(entities)
    texts = extract_texts(entities)
    print(f"✓ LINE 추출: {len(lines)}개")
    print(f"✓ TEXT/MTEXT 추출: {len(texts)}개")
    
    # 5. 화살표 탐지
    print("\n" + "=" * 80)
    print("5단계: 화살표 탐지")
    print("=" * 80)
    arrows = detect_arrows_in_drawing(lines, CONFIG)
    
    # 6. 지시화살표선 생성
    print("\n" + "=" * 80)
    print("6단계: 지시화살표선 생성")
    print("=" * 80)
    arrow_leaders = create_arrow_leaders(arrows)
    print(f"✓ 지시화살표선 생성: {len(arrow_leaders)}개")
    
    # 7. 텍스트 매칭
    print("\n" + "=" * 80)
    print("7단계: 텍스트 매칭")
    print("=" * 80)
    arrow_leaders = match_texts_to_arrows(arrow_leaders, texts, CONFIG)
    
    # 8. 지시경계선 탐지
    print("\n" + "=" * 80)
    print("8단계: 지시경계선 탐지")
    print("=" * 80)
    boundary_lines = detect_boundary_lines(arrow_leaders, lines, CONFIG)
    
    # 9. 보고서 생성
    print("\n" + "=" * 80)
    print("9단계: 보고서 생성")
    print("=" * 80)
    generate_report(doc, layers, entities, texts, arrows, arrow_leaders, 
                   boundary_lines, OUTPUT_REPORT)
    
    # 완료
    print("\n" + "=" * 80)
    print(" " * 30 + "분석 완료!")
    print("=" * 80)


if __name__ == "__main__":
    main()