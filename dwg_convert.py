"""
Wrapper para converter DWG -> DXF usando o binario dwg2dxf (LibreDWG).

O binario e' instalado no ambiente via Dockerfile (compilado a partir do
codigo-fonte do LibreDWG, projeto open source - https://www.gnu.org/software/libredwg/).
Se voce nao estiver rodando via Docker, instale o LibreDWG na maquina e garanta
que o comando `dwg2dxf` esteja no PATH (ou ajuste DWG2DXF_BIN abaixo / variavel
de ambiente DWG2DXF_BIN).
"""
import os
import shutil
import subprocess
import tempfile

DWG2DXF_BIN = os.environ.get("DWG2DXF_BIN", "dwg2dxf")


class DwgConversionError(RuntimeError):
    pass


def dwg2dxf_available() -> bool:
    return shutil.which(DWG2DXF_BIN) is not None


def convert_dwg_to_dxf(dwg_path: str, dxf_path: str = None, timeout: int = 120) -> str:
    """
    Converte um arquivo .dwg em .dxf. Retorna o caminho do .dxf gerado.
    Lanca DwgConversionError se o binario nao existir ou a conversao falhar.
    """
    if not dwg2dxf_available():
        raise DwgConversionError(
            "O conversor 'dwg2dxf' (LibreDWG) nao foi encontrado neste ambiente. "
            "Rode a aplicacao via Docker (o Dockerfile inclui a compilacao do "
            "LibreDWG) ou instale o LibreDWG localmente e garanta que 'dwg2dxf' "
            "esteja no PATH."
        )

    if dxf_path is None:
        fd, dxf_path = tempfile.mkstemp(suffix=".dxf")
        os.close(fd)

    result = subprocess.run(
        [DWG2DXF_BIN, dwg_path, "-o", dxf_path],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if not os.path.exists(dxf_path) or os.path.getsize(dxf_path) == 0:
        raise DwgConversionError(
            "Falha ao converter o DWG para DXF.\n"
            f"stdout: {result.stdout[-2000:]}\nstderr: {result.stderr[-2000:]}"
        )
    return dxf_path
