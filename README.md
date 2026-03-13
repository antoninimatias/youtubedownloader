# download_video.py

Script simples em Python para baixar um vídeo (ou playlist) na melhor qualidade usando `yt-dlp`.

Como usar:

1. Instale dependências:

```
python -m pip install -r requirements.txt
```

2. Baixe um vídeo:

```
python download_video.py "<URL_DO_VIDEO>" -o downloads
```

- `-o, --out`: diretório de saída (padrão: `.`)
- `-p, --playlist`: permitir download de playlists
- `-m, --merge`: formato de saída para merge (ex: `mp4`, `mkv`) — padrão `mp4`

Observação: para obter a melhor qualidade (vídeo e áudio separados que depois são mesclados), instale `ffmpeg` no sistema. Sem `ffmpeg` o script tentará baixar o melhor arquivo "progressivo" (vídeo+áudio já muxados), que pode ter qualidade inferior à combinação de melhor vídeo + melhor áudio.

Instalação rápida do `ffmpeg` no Windows (exemplo com Chocolatey):

```powershell
choco install ffmpeg -y
```

Ou baixe em: https://ffmpeg.org/download.html

- `-o, --out`: diretório de saída (padrão: `.`)
- `-p, --playlist`: permitir download de playlists
- `-m, --merge`: formato de saída para merge (ex: `mp4`, `mkv`) — padrão `mp4`

Exemplo:

```
python download_video.py https://www.youtube.com/watch?v=EXEMPLO -o meus_videos
```

## Politica de commit

Commite normalmente:

- `gui.py`
- `download_video.py`
- `requirements.txt`
- `BaixarVideo.spec`
- `assets/` (icones e imagens usadas pela aplicacao)
- `README.md`

Nao commitar (gerado localmente):

- `build/`
- `dist/`
- `downloads/`
- `__pycache__/` e `*.pyc`
- `.idea/` e outros arquivos locais de IDE
- backups como `gui.py.bak`

Obs.: as regras acima ja estao no arquivo `.gitignore` para evitar commit acidental.

