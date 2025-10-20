import ezdxf
from ezdxf.math import Vec3
from ezdxf.enums import TextEntityAlignment

def auto_add_dimensions_from_geometry(input_file, output_file):
    """
    DXF 파일의 형상을 분석하여 자동으로 치수 추가
    수치를 미리 알 필요 없이 파일만으로 치수 생성
    """
    
    print(f"\n{'='*60}")
    print(f"🔍 형상 분석 중: {input_file}")
    print(f"{'='*60}\n")
    
    # 1. 파일 로드
    doc = ezdxf.readfile(input_file)
    msp = doc.modelspace()
    
    # 2. 텍스트 스타일 설정
    if 'Standard' not in doc.styles:
        doc.styles.new('Standard', dxfattribs={'font': 'arial.ttf'})
    
    # 3. 치수 스타일 설정
    dimstyle = doc.dimstyles.new('AUTO_DIM')
    dimstyle.dxf.dimtxt = 5.0
    dimstyle.dxf.dimasz = 3.0
    dimstyle.dxf.dimexe = 2.0
    dimstyle.dxf.dimexo = 1.0
    dimstyle.dxf.dimtad = 1
    dimstyle.dxf.dimgap = 1.0
    dimstyle.dxf.dimtxsty = 'Standard'
    dimstyle.dxf.dimdec = 0
    
    # 4. 폴리라인(외곽선) 찾기 및 치수 추가
    polylines = list(msp.query('LWPOLYLINE'))
    
    if polylines:
        print("✅ 폴리라인 발견 - 외곽선 치수 추가 중...")
        
        for poly in polylines:
            points = list(poly.get_points())
            
            # 경계 계산
            x_coords = [p[0] for p in points]
            y_coords = [p[1] for p in points]
            
            min_x, max_x = min(x_coords), max(x_coords)
            min_y, max_y = min(y_coords), max(y_coords)
            
            width = max_x - min_x
            height = max_y - min_y
            
            print(f"  감지된 크기: {width:.1f} x {height:.1f} mm")
            
            # 수평 치수 (하단)
            if width > 1:  # 1mm 이상만
                dim_h = msp.add_linear_dim(
                    base=(min_x + width/2, min_y - 10, 0),
                    p1=(min_x, min_y, 0),
                    p2=(max_x, min_y, 0),
                    dimstyle='AUTO_DIM'
                )
                dim_h.render()
                print(f"    ✓ 수평 치수 추가: {width:.1f} mm")
            
            # 수직 치수 (좌측)
            if height > 1:
                dim_v = msp.add_linear_dim(
                    base=(min_x - 10, min_y + height/2, 0),
                    p1=(min_x, min_y, 0),
                    p2=(min_x, max_y, 0),
                    angle=90,
                    dimstyle='AUTO_DIM'
                )
                dim_v.render()
                print(f"    ✓ 수직 치수 추가: {height:.1f} mm")
    
    # 5. 원(구멍) 찾기 및 치수 추가
    circles = list(msp.query('CIRCLE'))
    
    if circles:
        print("\n✅ 원 발견 - 지름 치수 추가 중...")
        
        for i, circle in enumerate(circles):
            center = Vec3(circle.dxf.center)
            radius = circle.dxf.radius
            diameter = radius * 2
            
            print(f"  원 {i+1}: 지름 {diameter:.1f} mm")
            
            # 지름 치수 추가
            dim_d = msp.add_diameter_dim(
                center=(center.x, center.y, 0),
                radius=radius,
                angle=45,  # 45도 방향
                dimstyle='AUTO_DIM'
            )
            dim_d.render()
            print(f"    ✓ 지름 치수 추가: Ø{diameter:.1f} mm")
    
    # 6. 호(Arc) 찾기 및 치수 추가
    arcs = list(msp.query('ARC'))
    
    if arcs:
        print("\n✅ 호 발견 - 반지름 치수 추가 중...")
        
        for i, arc in enumerate(arcs):
            center = Vec3(arc.dxf.center)
            radius = arc.dxf.radius
            
            print(f"  호 {i+1}: 반지름 {radius:.1f} mm")
            
            # 반지름 치수 추가
            dim_r = msp.add_radius_dim(
                center=(center.x, center.y, 0),
                radius=radius,
                angle=arc.dxf.start_angle,
                dimstyle='AUTO_DIM'
            )
            dim_r.render()
            print(f"    ✓ 반지름 치수 추가: R{radius:.1f} mm")
    
    # 7. 개별 선(LINE) 분석 - 주요 선만
    lines = list(msp.query('LINE'))
    
    if lines:
        print(f"\n✅ 선 {len(lines)}개 발견")
        
        # 긴 수평선/수직선만 치수 추가
        for line in lines:
            start = Vec3(line.dxf.start)
            end = Vec3(line.dxf.end)
            length = start.distance(end)
            
            # 10mm 이상의 선만 치수 추가
            if length < 10:
                continue
            
            # 수평선
            if abs(start.y - end.y) < 0.1:
                dim = msp.add_linear_dim(
                    base=((start.x + end.x)/2, start.y - 5, 0),
                    p1=start,
                    p2=end,
                    dimstyle='AUTO_DIM'
                )
                dim.render()
                print(f"    ✓ 수평선 치수: {length:.1f} mm")
            
            # 수직선
            elif abs(start.x - end.x) < 0.1:
                dim = msp.add_linear_dim(
                    base=(start.x - 5, (start.y + end.y)/2, 0),
                    p1=start,
                    p2=end,
                    angle=90,
                    dimstyle='AUTO_DIM'
                )
                dim.render()
                print(f"    ✓ 수직선 치수: {length:.1f} mm")
    
    # 8. 정보 텍스트 추가
    info_text = msp.add_mtext(
        "AUTO-DIMENSIONED\nUnit: mm",
        dxfattribs={
            'char_height': 4,
            'style': 'Standard',
            'color': 3
        }
    )
    # 우측 상단에 배치 (대략적 위치)
    info_text.set_location((50, 100))
    
    # 9. 저장
    doc.saveas(output_file)
    
    print(f"\n{'='*60}")
    print(f"✅ 자동 치수 추가 완료!")
    print(f"📁 출력 파일: {output_file}")
    print(f"{'='*60}\n")


def analyze_and_dimension_all_views():
    """3개 뷰 모두 자동 분석 및 치수 추가"""
    
    files = [
        ('test_part_top.dxf', 'test_part_top_auto_dim.dxf', '평면도'),
        ('test_part_front.dxf', 'test_part_front_auto_dim.dxf', '정면도'),
        ('test_part_side.dxf', 'test_part_side_auto_dim.dxf', '측면도')
    ]
    
    print("\n" + "="*60)
    print("🤖 자동 치수 추가 시작 (3개 뷰)")
    print("="*60)
    
    for input_file, output_file, view_name in files:
        try:
            print(f"\n📋 처리 중: {view_name}")
            auto_add_dimensions_from_geometry(input_file, output_file)
        except FileNotFoundError:
            print(f"⚠️ 파일 없음: {input_file}")
        except Exception as e:
            print(f"❌ 오류: {e}")
    
    print("\n" + "="*60)
    print("🎉 모든 뷰 처리 완료!")
    print("="*60)


# 실행
if __name__ == "__main__":
    # 단일 파일 처리
    auto_add_dimensions_from_geometry(
        'test_part_top.dxf',
        'test_part_top_auto_dimensioned.dxf'
    )
    
    # 또는 모든 뷰 한번에 처리
    # analyze_and_dimension_all_views()