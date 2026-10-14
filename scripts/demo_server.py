#!/usr/bin/env python3
"""Start V2 with a disposable synthetic (or empty) case; nothing external."""
import argparse
from pathlib import Path
import shutil
import tempfile
from resume_server import StudioServer


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8875)
    parser.add_argument('--empty', action='store_true')
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='career-studio-demo-') as name:
        case = Path(name) / 'case'
        if args.empty:
            case.mkdir()
        else:
            shutil.copytree(Path(__file__).parents[1] / 'tests/fixtures/synthetic-case', case)
        with StudioServer(case, port=args.port) as server:
            print(f'合成数据本地工作台：http://127.0.0.1:{server.server_address[1]}；公开静态预览：/demo', flush=True)
            try: server.serve_forever()
            except KeyboardInterrupt: pass

if __name__ == '__main__': main()
