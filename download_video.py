import argparse
import os
import sys
import shutil
import subprocess
from yt_dlp import YoutubeDL


def progress_hook(d):
    status = d.get('status')
    if status == 'downloading':
        pct = d.get('_percent_str', '').strip()
        eta = d.get('_eta_str', '').strip()
        print(f"Baixando: {pct}  ETA: {eta}", end='\r')
    elif status == 'finished':
        print('\nDownload concluído — processando arquivo...')


def download(url, out_dir='.', allow_playlist=False, merge_format='mp4', ffmpeg_path=None):
    os.makedirs(out_dir, exist_ok=True)
    outtmpl = os.path.join(out_dir, '%(title)s [%(id)s].%(ext)s')
    # Permite que o usuário especifique o caminho do ffmpeg via argumento
    # CLI ou via variável de ambiente `FFMPEG_PATH`. Caso contrário, tenta
    # encontrá-lo no PATH.
    if not ffmpeg_path:
        # Prioriza variável de ambiente, depois PATH, depois caminhos comuns
        ffmpeg_path = os.environ.get('FFMPEG_PATH') or shutil.which('ffmpeg')
        if not ffmpeg_path:
            # Caminho detectado previamente no sistema do usuário
            common = r"C:\Users\anton\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmp eg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.0.1-full_build\bin\ffmpeg.exe"
            # Corrige espaços acidentais (caso tenham sido introduzidos)
            common = common.replace('FFmp eg', 'FFmpeg')
            if os.path.exists(common):
                ffmpeg_path = common
        if not ffmpeg_path:
            try:
                import imageio_ffmpeg
                ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()
            except Exception:
                pass
    ffmpeg_usable = False
    if ffmpeg_path:
        try:
            proc = subprocess.run([ffmpeg_path, '-version'], capture_output=True)
            ffmpeg_usable = proc.returncode == 0
        except Exception:
            ffmpeg_usable = False

    if ffmpeg_usable:
        print(f'Usando ffmpeg em: {ffmpeg_path}')
        ydl_opts = {
            'format': 'bestvideo+bestaudio/best',
            'outtmpl': outtmpl,
            'merge_output_format': merge_format,
            'ffmpeg_location': ffmpeg_path,
            'progress_hooks': [progress_hook],
            'noplaylist': not allow_playlist,
            'quiet': False,
            'no_warnings': True,
        }
    else:
        print('Aviso: ffmpeg não encontrado ou não funcional. Tentando baixar o melhor arquivo progressivo (com áudio).')
        print('Para obter a máxima qualidade (vídeo e áudio separados mesclados), instale/ajuste o PATH do ffmpeg e execute novamente.')
        # Seleciona o melhor formato que já contém áudio (progressive)
        ydl_opts = {
            'format': 'best[acodec!=none]/best',
            'outtmpl': outtmpl,
            'progress_hooks': [progress_hook],
            'noplaylist': not allow_playlist,
            'quiet': False,
            'no_warnings': True,
        }

    with YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])


def main(argv=None):
    parser = argparse.ArgumentParser(description='Baixa vídeo da URL na melhor qualidade')
    parser.add_argument('url', help='URL do vídeo ou playlist')
    parser.add_argument('-o', '--out', default='.', help='Diretório de saída')
    parser.add_argument('-p', '--playlist', action='store_true', help='Permitir download de playlist')
    parser.add_argument('-m', '--merge', default='mp4', help='Formato de saída para merge (ex: mp4, mkv)')
    parser.add_argument('--ffmpeg-path', help='Caminho para o executável ffmpeg (opcional). Também pode usar a variável de ambiente FFMPEG_PATH')

    args = parser.parse_args(argv)

    try:
        download(args.url, out_dir=args.out, allow_playlist=args.playlist, merge_format=args.merge, ffmpeg_path=args.ffmpeg_path)
    except Exception as e:
        print(f'Erro: {e}', file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
