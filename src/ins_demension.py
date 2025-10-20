"""
완전 자동화 워크플로우:
1. DXF 파일 읽기
2. 형상 자동 분석
3. 치수 자동 추가
4. 새 파일로 저장
"""

import sys
import argparse
import ezdxf
from ezdxf.math import Vec3
from ezdxf.enums import TextEntityAlignment


class DXFDimensionAnalyzer:
    """DXF 파일 치수 분석 및 자동 치수 추가 클래스"""
    
    def __init__(self, filename):
        self.filename = filename
        self.doc = ezdxf.readfile(filename)
        self.msp = self.doc.modelspace()
        self.dimensions = {}
        
    def analyze(self):
        """형상 분석하여 치수 추출"""
        print(f"\n🔍 분석 중: {self.filename}")
        
        # 외곽선 크기
        self._analyze_polylines()
        
        # 구멍 크기
        self._analyze_circles()
        
        # 호 크기
        self._analyze_arcs()
        
        return self.dimensions
    
    def _analyze_polylines(self):
        """폴리라인(외곽선) 분석"""
        polylines = list(self.msp.query('LWPOLYLINE'))
        
        if polylines:
            # 첫 번째 폴리라인을 주 외곽선으로 간주
            points = list(polylines[0].get_points())
            x_coords = [p[0] for p in points]
            y_coords = [p[1] for p in points]
            
            self.dimensions['bbox'] = {
                'min_x': min(x_coords),
                'max_x': max(x_coords),
                'min_y': min(y_coords),
                'max_y': max(y_coords),
                'width': max(x_coords) - min(x_coords),
                'height': max(y_coords) - min(y_coords)
            }
            
            print(f"  📐 외곽선: {self.dimensions['bbox']['width']:.1f} x {self.dimensions['bbox']['height']:.1f} mm")
    
    def _analyze_circles(self):
        """원(구멍) 분석"""
        circles = list(self.msp.query('CIRCLE'))
        
        self.dimensions['circles'] = []
        for circle in circles:
            center = Vec3(circle.dxf.center)
            radius = circle.dxf.radius
            
            self.dimensions['circles'].append({
                'center': (center.x, center.y),
                'radius': radius,
                'diameter': radius * 2
            })
            
            print(f"  ⭕ 구멍: Ø{radius * 2:.1f} mm @ ({center.x:.1f}, {center.y:.1f})")
    
    def _analyze_arcs(self):
        """호 분석"""
        arcs = list(self.msp.query('ARC'))
        
        self.dimensions['arcs'] = []
        for arc in arcs:
            center = Vec3(arc.dxf.center)
            radius = arc.dxf.radius
            
            self.dimensions['arcs'].append({
                'center': (center.x, center.y),
                'radius': radius
            })
            
            print(f"  🌙 호: R{radius:.1f} mm")
    
    def add_dimensions_and_save(self, output_file):
        """분석 결과를 바탕으로 치수 추가 후 저장"""
        
        print(f"\n📝 치수 추가 중...")
        
        # 스타일 설정
        if 'Standard' not in self.doc.styles:
            self.doc.styles.new('Standard', dxfattribs={'font': 'arial.ttf'})
        
        dimstyle = self.doc.dimstyles.new('AUTO')
        dimstyle.dxf.dimtxt = 5.0
        dimstyle.dxf.dimasz = 3.0
        dimstyle.dxf.dimexe = 2.0
        dimstyle.dxf.dimexo = 1.0
        dimstyle.dxf.dimtad = 1
        dimstyle.dxf.dimgap = 1.0
        dimstyle.dxf.dimtxsty = 'Standard'
        dimstyle.dxf.dimdec = 0
        
        # 외곽선 치수
        if 'bbox' in self.dimensions:
            bbox = self.dimensions['bbox']
            
            # 수평 치수
            dim_h = self.msp.add_linear_dim(
                base=(0, bbox['min_y'] - 10, 0),
                p1=(bbox['min_x'], bbox['min_y'], 0),
                p2=(bbox['max_x'], bbox['min_y'], 0),
                dimstyle='AUTO'
            )
            dim_h.render()
            print(f"  ✓ 폭: {bbox['width']:.1f} mm")
            
            # 수직 치수
            dim_v = self.msp.add_linear_dim(
                base=(bbox['min_x'] - 10, 0, 0),
                p1=(bbox['min_x'], bbox['min_y'], 0),
                p2=(bbox['min_x'], bbox['max_y'], 0),
                angle=90,
                dimstyle='AUTO'
            )
            dim_v.render()
            print(f"  ✓ 높이: {bbox['height']:.1f} mm")
        
        # 원 치수
        for circle in self.dimensions.get('circles', []):
            dim_d = self.msp.add_diameter_dim(
                center=circle['center'] + (0,),
                radius=circle['radius'],
                angle=45,
                dimstyle='AUTO'
            )
            dim_d.render()
            print(f"  ✓ 지름: Ø{circle['diameter']:.1f} mm")
        
        # 호 치수
        for arc in self.dimensions.get('arcs', []):
            dim_r = self.msp.add_radius_dim(
                center=arc['center'] + (0,),
                radius=arc['radius'],
                angle=45,
                dimstyle='AUTO'
            )
            dim_r.render()
            print(f"  ✓ 반지름: R{arc['radius']:.1f} mm")
        
        # 저장
        self.doc.saveas(output_file)
        print(f"\n✅ 저장 완료: {output_file}")
    
    def print_summary(self):
        """분석 결과 요약 출력"""
        print(f"\n{'='*60}")
        print("📊 분석 결과 요약")
        print(f"{'='*60}")
        
        if 'bbox' in self.dimensions:
            print(f"외곽선:")
            print(f"  폭: {self.dimensions['bbox']['width']:.2f} mm")
            print(f"  높이: {self.dimensions['bbox']['height']:.2f} mm")
        
        if self.dimensions.get('circles'):
            print(f"\n구멍: {len(self.dimensions['circles'])}개")
            for i, c in enumerate(self.dimensions['circles'], 1):
                print(f"  {i}. Ø{c['diameter']:.2f} mm")
        
        if self.dimensions.get('arcs'):
            print(f"\n호: {len(self.dimensions['arcs'])}개")
            for i, a in enumerate(self.dimensions['arcs'], 1):
                print(f"  {i}. R{a['radius']:.2f} mm")
        
        print(f"{'='*60}\n")


def process_single_file(input_file, output_file):
    """단일 파일 처리"""
    
    # 1. 분석
    analyzer = DXFDimensionAnalyzer(input_file)
    dimensions = analyzer.analyze()
    
    # 2. 요약 출력
    analyzer.print_summary()
    
    # 3. 치수 추가 및 저장
    analyzer.add_dimensions_and_save(output_file)
    
    return dimensions


def main():
    """메인 함수 - CLI 인자 처리"""
    
    parser = argparse.ArgumentParser(
        description='DXF 파일에 자동으로 치수를 추가하는 프로그램',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
사용 예시:
  %(prog)s -i input.dxf
  %(prog)s -i input.dxf -o output.dxf
  %(prog)s --input test.dxf --output result.dxf
        """
    )
    
    parser.add_argument(
        '-i', '--input',
        dest='input_file',
        required=True,
        help='입력 DXF 파일 경로 (필수)'
    )
    
    parser.add_argument(
        '-o', '--output',
        dest='output_file',
        default='output.dxf',
        help='출력 DXF 파일 경로 (기본값: output.dxf)'
    )
    
    # 인자가 없으면 도움말 표시
    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(1)
    
    args = parser.parse_args()
    
    # 파일 처리
    try:
        print("="*60)
        print("🚀 DXF 자동 치수 추가 프로그램")
        print("="*60)
        print(f"입력 파일: {args.input_file}")
        print(f"출력 파일: {args.output_file}")
        
        dimensions = process_single_file(args.input_file, args.output_file)
        
        # 추출된 치수 활용
        if dimensions and 'bbox' in dimensions:
            width = dimensions['bbox']['width']
            height = dimensions['bbox']['height']
            
            print(f"\n💡 추출된 치수:")
            print(f"   폭: {width:.2f} mm")
            print(f"   높이: {height:.2f} mm")
            
            if dimensions.get('circles'):
                hole_diameter = dimensions['circles'][0]['diameter']
                print(f"   구멍 지름: Ø{hole_diameter:.2f} mm")
        
        print("\n🎉 처리 완료!")
        
    except FileNotFoundError:
        print(f"\n❌ 오류: 파일을 찾을 수 없습니다 - {args.input_file}")
        sys.exit(1)
    except ezdxf.DXFError as e:
        print(f"\n❌ DXF 오류: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 예상치 못한 오류: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()