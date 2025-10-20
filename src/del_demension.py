"""
DXF 파일에서 치수표기 및 주석을 제거하고 다른 파일로 저장 (CLI 버전)

사용법:
    python del_demension.py -i input.dxf                    # 치수+주석 모두 제거 (기본)
    python del_demension.py -i input.dxf -o output.dxf      # 출력 파일명 지정
    python del_demension.py -i input.dxf --only-dimensions  # 치수만 제거
    python del_demension.py -i input.dxf --only-annotations # 주석만 제거
"""

import ezdxf
import argparse
from pathlib import Path


class DXFCleaner:
    """DXF 파일 정리 클래스"""
    
    def __init__(self, input_file):
        """
        Parameters:
            input_file: 입력 DXF 파일 경로
        """
        self.input_file = Path(input_file)
        self.doc = None
        self.removed_count = {
            'dimensions': 0,
            'texts': 0,
            'mtexts': 0,
            'leaders': 0,
            'multileaders': 0,
            'total': 0
        }
        
    def load(self):
        """DXF 파일 로드"""
        try:
            self.doc = ezdxf.readfile(str(self.input_file))
            print(f"✅ 파일 로드 성공: {self.input_file}")
            return True
        except Exception as e:
            print(f"❌ 파일 로드 실패: {e}")
            return False
    
    def remove_dimensions(self, remove_dimension_blocks=True):
        """
        치수 제거 (보조선, 화살표 포함)
        
        Parameters:
            remove_dimension_blocks: 치수 블록 정의도 제거 여부
        """
        if not self.doc:
            print("❌ 문서가 로드되지 않았습니다.")
            return 0
        
        msp = self.doc.modelspace()
        count = 0
        
        # 1. DIMENSION 엔티티 찾기 및 삭제
        dimensions = list(msp.query('DIMENSION'))
        for dim in dimensions:
            msp.delete_entity(dim)
            count += 1
        
        print(f"  🗑️ 치수(DIMENSION) 엔티티: {count}개")
        
        # 2. 분해된 치수 구성요소 제거
        # 치수가 explode되면 LINE, SOLID, INSERT 등으로 분해됨
        
        # 화살표 (SOLID 엔티티 - 작은 삼각형)
        solids = list(msp.query('SOLID'))
        arrow_count = 0
        for solid in solids:
            # 작은 SOLID는 화살표일 가능성이 높음
            try:
                vertices = [solid.dxf.vtx0, solid.dxf.vtx1, solid.dxf.vtx2, solid.dxf.vtx3]
                # 크기 계산
                x_coords = [v[0] for v in vertices]
                y_coords = [v[1] for v in vertices]
                width = max(x_coords) - min(x_coords)
                height = max(y_coords) - min(y_coords)
                size = max(width, height)
                
                # 10mm 이하의 작은 SOLID는 화살표로 간주
                if size < 10:
                    msp.delete_entity(solid)
                    arrow_count += 1
            except:
                pass
        
        if arrow_count > 0:
            print(f"  🗑️ 화살표(SOLID): {arrow_count}개")
            count += arrow_count
        
        # 3. 치수선 관련 작은 LINE 제거 (선택적)
        lines = list(msp.query('LINE'))
        dim_line_count = 0
        for line in lines:
            try:
                # 레이어 이름에 'DIM', 'DIMENSION' 포함된 경우
                layer_name = line.dxf.layer.upper()
                if 'DIM' in layer_name or 'DIMENSION' in layer_name:
                    msp.delete_entity(line)
                    dim_line_count += 1
            except:
                pass
        
        if dim_line_count > 0:
            print(f"  🗑️ 치수 레이어 선(LINE): {dim_line_count}개")
            count += dim_line_count
        
        # 4. 치수 블록 정의 제거
        if remove_dimension_blocks:
            block_count = 0
            blocks_to_remove = []
            
            for block in self.doc.blocks:
                block_name = block.name.upper()
                # 일반적인 치수 블록 이름 패턴
                if any(pattern in block_name for pattern in ['_DIM', 'DIMENSION', '_ARROW', 'DIMBLK']):
                    blocks_to_remove.append(block.name)
                    block_count += 1
            
            for block_name in blocks_to_remove:
                try:
                    self.doc.blocks.delete_block(block_name, safe=False)
                except:
                    pass
            
            if block_count > 0:
                print(f"  🗑️ 치수 블록 정의: {block_count}개")
        
        # 5. INSERT 엔티티 중 치수 관련 제거
        inserts = list(msp.query('INSERT'))
        insert_count = 0
        for insert in inserts:
            try:
                block_name = insert.dxf.name.upper()
                if any(pattern in block_name for pattern in ['_DIM', 'DIMENSION', '_ARROW', 'DIMBLK']):
                    msp.delete_entity(insert)
                    insert_count += 1
            except:
                pass
        
        if insert_count > 0:
            print(f"  🗑️ 치수 블록 참조(INSERT): {insert_count}개")
            count += insert_count
        
        # 6. 치수 레이어 제거
        layer_count = 0
        entity_count = 0
        dim_layer_patterns = ['DIM', 'DIMENSION', 'DEFPOINTS']
        
        layers_to_remove = []
        for layer in self.doc.layers:
            layer_name_upper = layer.dxf.name.upper()
            if any(pattern in layer_name_upper for pattern in dim_layer_patterns):
                layers_to_remove.append(layer.dxf.name)
        
        for layer_name in layers_to_remove:
            entities = list(msp.query(f'*[layer=="{layer_name}"]'))
            for entity in entities:
                try:
                    msp.delete_entity(entity)
                    entity_count += 1
                except:
                    pass
            layer_count += 1
        
        for layer_name in layers_to_remove:
            try:
                self.doc.layers.remove(layer_name)
            except:
                pass
        
        if layer_count > 0:
            print(f"  🗑️ 치수 레이어: {layer_count}개 ({entity_count}개 엔티티)")
            count += entity_count
        
        self.removed_count['dimensions'] = count
        print(f"  ✅ 총 치수 관련 제거: {count}개")
        
        return count
    
    def remove_annotations(self):
        """주석(텍스트, 지시선 등) 제거"""
        if not self.doc:
            print("❌ 문서가 로드되지 않았습니다.")
            return 0
        
        msp = self.doc.modelspace()
        total = 0
        
        # TEXT 제거
        texts = list(msp.query('TEXT'))
        for text in texts:
            msp.delete_entity(text)
            self.removed_count['texts'] += 1
        print(f"  🗑️ 텍스트(TEXT): {len(texts)}개")
        total += len(texts)
        
        # MTEXT 제거
        mtexts = list(msp.query('MTEXT'))
        for mtext in mtexts:
            msp.delete_entity(mtext)
            self.removed_count['mtexts'] += 1
        print(f"  🗑️ 멀티텍스트(MTEXT): {len(mtexts)}개")
        total += len(mtexts)
        
        # LEADER 제거
        leaders = list(msp.query('LEADER'))
        for leader in leaders:
            msp.delete_entity(leader)
            self.removed_count['leaders'] += 1
        print(f"  🗑️ 지시선(LEADER): {len(leaders)}개")
        total += len(leaders)
        
        # MULTILEADER 제거
        try:
            multileaders = list(msp.query('MULTILEADER'))
            for mleader in multileaders:
                msp.delete_entity(mleader)
                self.removed_count['multileaders'] += 1
            print(f"  🗑️ 다중지시선(MULTILEADER): {len(multileaders)}개")
            total += len(multileaders)
        except:
            pass
        
        return total
    
    def remove_auxiliary_lines(self, search_radius=50.0):
        """
        치수 보조선 제거 (TEXT 주변의 치수선과 화살표 제거)
        - 직선 보조선: 수평/수직 직선 + 화살표
        - 한번 꺾인 보조선: 연결된 2개 직선 + 화살표
        
        Parameters:
            search_radius: TEXT 주변 탐색 반경 (mm)
        
        Returns:
            제거된 개수
        """
        if not self.doc:
            print("❌ 문서가 로드되지 않았습니다.")
            return 0
        
        msp = self.doc.modelspace()
        
        # 로그 파일 열기
        log_file = open('output.txt', 'w', encoding='utf-8')
        log_file.write("="*80 + "\n")
        log_file.write("치수 보조선 탐색 로그\n")
        log_file.write("="*80 + "\n\n")
        
        # 1. 모든 TEXT 위치 수집
        text_positions = []
        for text in msp.query('TEXT'):
            try:
                pos = text.dxf.insert
                text_positions.append({
                    'pos': (pos.x, pos.y),
                    'text': text.dxf.text
                })
            except:
                pass
        
        for mtext in msp.query('MTEXT'):
            try:
                pos = mtext.dxf.insert
                text_positions.append({
                    'pos': (pos.x, pos.y),
                    'text': mtext.text[:20]  # 처음 20자만
                })
            except:
                pass
        
        if not text_positions:
            print("  ℹ️ TEXT가 없어 보조선 제거를 건너뜁니다")
            log_file.close()
            return 0
        
        print(f"  📍 TEXT 위치 {len(text_positions)}개 발견")
        log_file.write(f"TEXT 위치 {len(text_positions)}개 발견\n\n")
        
        # 2. 화살표(SOLID) 수집
        arrows = []
        for solid in msp.query('SOLID'):
            try:
                vertices = [solid.dxf.vtx0, solid.dxf.vtx1, solid.dxf.vtx2, solid.dxf.vtx3]
                center_x = sum(v[0] for v in vertices) / 4
                center_y = sum(v[1] for v in vertices) / 4
                arrows.append({
                    'entity': solid,
                    'center': (center_x, center_y)
                })
            except:
                pass
        
        print(f"  🎯 화살표(SOLID) {len(arrows)}개 발견")
        log_file.write(f"화살표(SOLID) {len(arrows)}개 발견\n\n")
        
        # 3. LINE 수집
        lines = list(msp.query('LINE'))
        line_data = []
        
        for line in lines:
            try:
                start = line.dxf.start
                end = line.dxf.end
                line_data.append({
                    'entity': line,
                    'start': (start.x, start.y),
                    'end': (end.x, end.y),
                    'length': ((end.x - start.x)**2 + (end.y - start.y)**2)**0.5
                })
            except:
                pass
        
        print(f"  📏 LINE {len(line_data)}개 발견")
        log_file.write(f"LINE {len(line_data)}개 발견\n\n")
        
        # 4. 사전 필터링: 화살표가 붙은 선들만 추출
        print(f"  🔍 사전 필터링 중... (화살표 연결 확인)")
        log_file.write("="*80 + "\n")
        log_file.write("1단계: 화살표가 붙은 LINE 사전 필터링\n")
        log_file.write("="*80 + "\n\n")
        
        auxiliary_candidates = self._build_auxiliary_candidates(
            line_data, arrows, log_file
        )
        
        print(f"  ✅ 보조선 후보 {len(auxiliary_candidates)}개 발견")
        log_file.write(f"\n총 보조선 후보: {len(auxiliary_candidates)}개\n\n")
        
        # 5. TEXT 주변 탐색
        print(f"  🔍 TEXT 주변 탐색 시작 (반경 {search_radius}mm)")
        log_file.write("="*80 + "\n")
        log_file.write(f"2단계: TEXT 주변 탐색 (반경 {search_radius}mm)\n")
        log_file.write("="*80 + "\n\n")
        
        lines_to_remove = set()
        arrows_to_remove = set()
        
        for idx, text_info in enumerate(text_positions, 1):
            tx, ty = text_info['pos']
            text_content = text_info['text']
            
            log_file.write(f"[{idx}/{len(text_positions)}] TEXT: '{text_content}' @ ({tx:.2f}, {ty:.2f})\n")
            
            found_count = 0
            
            # 후보 리스트에서만 검색
            for candidate in auxiliary_candidates:
                start_x, start_y = candidate['start_point']
                dist = ((start_x - tx)**2 + (start_y - ty)**2)**0.5
                
                if dist <= search_radius:
                    found_count += 1
                    
                    # 선들 제거 표시
                    for line in candidate['lines']:
                        lines_to_remove.add(id(line['entity']))
                    
                    # 화살표 제거 표시
                    arrows_to_remove.add(id(candidate['arrow']['entity']))
                    
                    log_file.write(f"  → 보조선 발견! 거리: {dist:.2f}mm, ")
                    log_file.write(f"선 개수: {len(candidate['lines'])}개, ")
                    log_file.write(f"시작점: ({start_x:.2f}, {start_y:.2f})\n")
            
            if found_count > 0:
                print(f"    TEXT {idx}/{len(text_positions)} → 보조선 {found_count}개 발견")
                log_file.write(f"  결과: 보조선 {found_count}개 발견\n\n")
            else:
                log_file.write(f"  결과: 보조선 없음\n\n")
        
        # 6. 제거 실행
        removed_lines = 0
        for ld in line_data:
            if id(ld['entity']) in lines_to_remove:
                try:
                    msp.delete_entity(ld['entity'])
                    removed_lines += 1
                except:
                    pass
        
        removed_arrows = 0
        for arrow in arrows:
            if id(arrow['entity']) in arrows_to_remove:
                try:
                    msp.delete_entity(arrow['entity'])
                    removed_arrows += 1
                except:
                    pass
        
        total = removed_lines + removed_arrows
        
        log_file.write("="*80 + "\n")
        log_file.write("최종 결과\n")
        log_file.write("="*80 + "\n")
        log_file.write(f"제거된 LINE: {removed_lines}개\n")
        log_file.write(f"제거된 화살표: {removed_arrows}개\n")
        log_file.write(f"총 제거: {total}개\n")
        log_file.close()
        
        if removed_lines > 0:
            print(f"  🗑️ 치수선(LINE): {removed_lines}개")
        if removed_arrows > 0:
            print(f"  🗑️ 화살표(SOLID): {removed_arrows}개")
        
        print(f"  ✅ 총 보조선 관련: {total}개")
        print(f"  📄 상세 로그: output.txt")
        
        return total
    
    def _build_auxiliary_candidates(self, line_data, arrows, log_file):
        """
        화살표가 붙은 선들을 사전 필터링하여 보조선 후보 리스트 생성
        """
        candidates = []
        
        for idx, line in enumerate(line_data):
            # 화살표가 끝점에 붙어있는지 확인
            arrow_at_start = None
            arrow_at_end = None
            
            for arrow in arrows:
                ax, ay = arrow['center']
                
                dist_to_start = ((ax - line['start'][0])**2 + (ay - line['start'][1])**2)**0.5
                dist_to_end = ((ax - line['end'][0])**2 + (ay - line['end'][1])**2)**0.5
                
                if dist_to_start <= 5:
                    arrow_at_start = arrow
                if dist_to_end <= 5:
                    arrow_at_end = arrow
            
            # 화살표가 있는 경우만 처리
            if arrow_at_start or arrow_at_end:
                # 화살표 반대쪽이 임시 시작점
                if arrow_at_end:
                    temp_start = line['start']
                    arrow_point = line['end']
                    current_arrow = arrow_at_end
                else:
                    temp_start = line['end']
                    arrow_point = line['start']
                    current_arrow = arrow_at_start
                
                # 임시 시작점에 다른 선이 연결되어 있는지 확인 (한번 꺾인 보조선)
                connected_line = None
                for other_line in line_data:
                    if id(other_line['entity']) == id(line['entity']):
                        continue
                    
                    # 임시 시작점과 가까운 점이 있는지
                    dist_to_start = ((other_line['start'][0] - temp_start[0])**2 + 
                                    (other_line['start'][1] - temp_start[1])**2)**0.5
                    dist_to_end = ((other_line['end'][0] - temp_start[0])**2 + 
                                  (other_line['end'][1] - temp_start[1])**2)**0.5
                    
                    if dist_to_start <= 3:
                        # 각도가 다른지 확인
                        if self._is_different_angle(line, other_line):
                            connected_line = other_line
                            final_start = other_line['end']
                            break
                    elif dist_to_end <= 3:
                        if self._is_different_angle(line, other_line):
                            connected_line = other_line
                            final_start = other_line['start']
                            break
                
                # 후보 등록
                if connected_line:
                    # 한번 꺾인 보조선
                    candidates.append({
                        'lines': [line, connected_line],
                        'start_point': final_start,
                        'arrow': current_arrow,
                        'type': 'bent'
                    })
                    log_file.write(f"후보 {len(candidates)}: 한번 꺾인 보조선 ")
                    log_file.write(f"시작점({final_start[0]:.2f}, {final_start[1]:.2f})\n")
                else:
                    # 직선 보조선
                    candidates.append({
                        'lines': [line],
                        'start_point': temp_start,
                        'arrow': current_arrow,
                        'type': 'straight'
                    })
                    log_file.write(f"후보 {len(candidates)}: 직선 보조선 ")
                    log_file.write(f"시작점({temp_start[0]:.2f}, {temp_start[1]:.2f})\n")
        
        return candidates
    
    def _is_different_angle(self, line1, line2, angle_threshold=10):
        """두 선의 각도가 충분히 다른지 확인 (10도 이상 차이)"""
        import math
        
        # line1의 각도
        dx1 = line1['end'][0] - line1['start'][0]
        dy1 = line1['end'][1] - line1['start'][1]
        angle1 = math.atan2(dy1, dx1) * 180 / math.pi
        
        # line2의 각도
        dx2 = line2['end'][0] - line2['start'][0]
        dy2 = line2['end'][1] - line2['start'][1]
        angle2 = math.atan2(dy2, dx2) * 180 / math.pi
        
        # 각도 차이
        diff = abs(angle1 - angle2)
        if diff > 180:
            diff = 360 - diff
        
        return diff >= angle_threshold
    
    def _check_arrow_at_line_end(self, line_data, arrows, arrows_to_remove):
        """선 끝에 화살표가 있는지 확인 (레거시 함수 - 사용 안 함)"""
        # 이 함수는 더 이상 사용하지 않음
        pass
    
    def _find_bent_auxiliary_lines(self, text_pos, search_radius, line_data, 
                                   arrows, lines_to_remove, arrows_to_remove):
        """레거시 함수 - 사용 안 함"""
        # 이 함수는 더 이상 사용하지 않음
        pass
    
    def _are_lines_connected(self, line1, line2, tolerance=3.0):
        """레거시 함수 - 사용 안 함"""
        # 이 함수는 더 이상 사용하지 않음
        pass
    
    def _get_other_end(self, line, connect_point):
        """레거시 함수 - 사용 안 함"""
        # 이 함수는 더 이상 사용하지 않음
        pass
    
    def clean(self, remove_dimensions=True, remove_annotations=True, 
              remove_auxiliary=False, search_radius=50.0):
        """
        치수 및 주석 제거
        
        Parameters:
            remove_dimensions: 치수 제거 여부
            remove_annotations: 주석 제거 여부
            remove_auxiliary: 보조선 제거 여부
            search_radius: TEXT 주변 탐색 반경 (mm)
        
        Returns:
            제거된 총 개수
        """
        print(f"\n{'='*60}")
        print(f"🧹 DXF 정리 시작")
        print(f"{'='*60}")
        
        total_removed = 0
        
        # 중요: 보조선 제거는 TEXT가 삭제되기 BEFORE에 실행해야 함!
        if remove_auxiliary:
            print(f"\n📐 치수 보조선 제거 중... (TEXT 위치 기반)")
            print(f"  💡 방법: TEXT 주변 {search_radius}mm 반경 내 수평/수직선 + 화살표 탐지")
            total_removed += self.remove_auxiliary_lines(search_radius=search_radius)
        
        if remove_dimensions:
            print("\n📏 치수 제거 중...")
            total_removed += self.remove_dimensions(remove_dimension_blocks=True)
        
        if remove_annotations:
            print("\n📝 주석(TEXT) 제거 중...")
            total_removed += self.remove_annotations()
        
        self.removed_count['total'] = total_removed
        
        print(f"\n{'='*60}")
        print(f"✅ 총 {total_removed}개 엔티티 제거 완료")
        print(f"{'='*60}\n")
        
        return total_removed
    
    def save(self, output_file):
        """정리된 파일 저장"""
        if not self.doc:
            print("❌ 저장할 문서가 없습니다.")
            return False
        
        try:
            output_path = Path(output_file)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            self.doc.saveas(str(output_path))
            print(f"💾 저장 완료: {output_path}")
            return True
        except Exception as e:
            print(f"❌ 저장 실패: {e}")
            return False
    
    def get_statistics(self):
        """현재 문서의 통계"""
        if not self.doc:
            return None
        
        msp = self.doc.modelspace()
        
        stats = {
            'dimensions': len(list(msp.query('DIMENSION'))),
            'texts': len(list(msp.query('TEXT'))),
            'mtexts': len(list(msp.query('MTEXT'))),
            'leaders': len(list(msp.query('LEADER'))),
            'lines': len(list(msp.query('LINE'))),
            'circles': len(list(msp.query('CIRCLE'))),
            'polylines': len(list(msp.query('LWPOLYLINE'))),
            'arcs': len(list(msp.query('ARC')))
        }
        
        return stats
    
    def print_summary(self):
        """정리 결과 요약"""
        print(f"\n{'='*60}")
        print("📊 정리 결과 요약")
        print(f"{'='*60}")
        print(f"  치수 제거: {self.removed_count['dimensions']}개")
        print(f"  텍스트 제거: {self.removed_count['texts']}개")
        print(f"  멀티텍스트 제거: {self.removed_count['mtexts']}개")
        print(f"  지시선 제거: {self.removed_count['leaders']}개")
        print(f"  다중지시선 제거: {self.removed_count['multileaders']}개")
        print(f"  {'─'*58}")
        print(f"  총 제거: {self.removed_count['total']}개")
        print(f"{'='*60}\n")


def process_file(input_file, output_file, 
                remove_dimensions=True, 
                remove_annotations=True,
                remove_auxiliary=False,
                search_radius=50.0):
    """
    DXF 파일 처리 메인 함수
    
    Parameters:
        input_file: 입력 파일 경로
        output_file: 출력 파일 경로
        remove_dimensions: 치수 제거 여부
        remove_annotations: 주석 제거 여부
        remove_auxiliary: 보조선 제거 여부
        search_radius: TEXT 주변 탐색 반경 (mm)
    
    Returns:
        성공 여부 (bool)
    """
    
    print(f"\n{'='*60}")
    print(f"📁 입력 파일: {input_file}")
    print(f"📄 출력 파일: {output_file}")
    
    # 제거 모드 표시
    modes = []
    if remove_dimensions:
        modes.append("치수")
    if remove_annotations:
        modes.append("주석")
    if remove_auxiliary:
        modes.append(f"보조선(TEXT 반경 {search_radius}mm)")
    
    if modes:
        print(f"🔧 모드: {' + '.join(modes)} 제거")
    else:
        print(f"⚠️ 경고: 아무것도 제거하지 않습니다")
    
    print(f"{'='*60}\n")
    
    # Cleaner 생성 및 로드
    cleaner = DXFCleaner(input_file)
    
    if not cleaner.load():
        return False
    
    # 정리 전 통계
    print("\n📈 정리 전 통계:")
    before_stats = cleaner.get_statistics()
    for key, value in before_stats.items():
        print(f"  {key}: {value}개")
    
    # 정리 실행
    cleaner.clean(remove_dimensions=remove_dimensions, 
                 remove_annotations=remove_annotations,
                 remove_auxiliary=remove_auxiliary,
                 search_radius=search_radius)
    
    # 결과 요약
    cleaner.print_summary()
    
    # 저장
    success = cleaner.save(output_file)
    
    if success:
        print(f"\n🎉 처리 완료!")
    
    return success


def main():
    """CLI 메인 함수"""
    
    parser = argparse.ArgumentParser(
        description='DXF 파일에서 치수 및 주석을 제거하는 도구',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
사용 예시:
  # 기본: 치수 + 주석 모두 제거
  python %(prog)s -i input.dxf
  python %(prog)s -i input.dxf -o output.dxf
  
  # 치수만 제거
  python %(prog)s -i input.dxf --only-dimensions
  
  # 주석만 제거
  python %(prog)s -i input.dxf --only-annotations
  
  # 주석 + 보조선 제거 (치수 숫자와 보조선 모두 제거)
  python %(prog)s -i input.dxf --remove-auxiliary-lines
  
  # 탐색 반경 변경 (TEXT 주변 30mm 내 보조선만 제거)
  python %(prog)s -i input.dxf --remove-auxiliary-lines --search-radius 30.0
        """
    )
    
    # 필수 인자
    parser.add_argument(
        '-i', '--input',
        dest='input_file',
        #required=True,
        help='입력 DXF 파일 경로 (필수)'
    )
    
    # 선택 인자
    parser.add_argument(
        '-o', '--output',
        dest='output_file',
        default='output.dxf',
        help='출력 DXF 파일 경로 (기본값: output.dxf)'
    )
    
    parser.add_argument(
        '--only-dimensions',
        action='store_true',
        help='치수만 제거 (주석은 유지)'
    )
    
    parser.add_argument(
        '--only-annotations',
        action='store_true',
        help='주석만 제거 (치수는 유지)'
    )
    
    parser.add_argument(
        '--remove-auxiliary-lines',
        action='store_true',
        help='치수 보조선 제거 (5mm 이하 작은 LINE 제거)'
    )
    
    parser.add_argument(
        '--line-threshold',
        type=float,
        default=5.0,
        help='보조선 판단 기준 길이 (mm, 기본값: 5.0)'
    )
    
    # 인자 파싱
    # args = parser.parse_args()
    input_file = "data\\gear-disk\\Gear Disk dxf File.dxf"
    output_file = "data\\gear-disk\\output.dxf"
    only_dimensions = False
    only_annotations = False
    remove_auxiliary_lines = True
    search_radius = 30.0
    
    # 파일 존재 확인
    input_path = Path(input_file)
    if not input_path.exists():
        print(f"❌ 오류: 파일을 찾을 수 없습니다: {input_file}")
        return 1
    
    if not input_path.suffix.lower() == '.dxf':
        print(f"⚠️ 경고: DXF 파일이 아닙니다: {input_file}")
    
    # 제거 옵션 결정
    if only_dimensions:
        # 치수만 제거
        remove_dims = True
        remove_anns = False
    elif only_annotations:
        # 주석만 제거
        remove_dims = False
        remove_anns = True
    else:
        # 기본: 둘 다 제거
        remove_dims = True
        remove_anns = True
    
    # 보조선 제거 옵션
    remove_aux = remove_auxiliary_lines
    search_rad = search_radius
    
    # 처리 실행
    success = process_file(
        input_file=input_file,
        output_file=output_file,
        remove_dimensions=remove_dims,
        remove_annotations=remove_anns,
        remove_auxiliary=remove_aux,
        search_radius=search_rad
    )
    
    return 0 if success else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())