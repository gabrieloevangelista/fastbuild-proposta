"""
Motor de calculo do orcamento de instalacao.

Regra de negocio (conforme definido por Gabriel/FastBuild):
    valor_instalacao = metragem_total_de_parede_confirmada (m) x valor_por_metro (R$)

O motor NUNCA calcula em cima do numero "bruto" do algoritmo de deteccao de
paredes (wall_extract.py) sem que esse numero tenha passado pela etapa de
confirmacao humana (tela de revisao). Isso evita que hachuras, simbolos ou
falhas de geometria virem dinheiro errado na proposta.
"""
from dataclasses import dataclass, field


DEFAULT_RATE_PER_METER = 150.00  # R$/m - instalacao


@dataclass
class FloorMeasurement:
    """Metragem confirmada de um pavimento (apos revisao humana)."""
    name: str                  # ex: "Terreo"
    confirmed_length_m: float  # metragem que o usuario confirmou na tela de revisao
    auto_high_confidence_m: float = 0.0   # o que o algoritmo detectou com confianca alta (referencia)
    auto_needs_review_m: float = 0.0      # o que ficou como "candidato a revisar" (referencia)
    notes: str = ""


@dataclass
class BudgetResult:
    floors: list
    rate_per_meter: float
    total_length_m: float
    total_value: float

    def as_rows(self):
        """Linhas prontas para a tabela do PDF: (pavimento, metros, valor)."""
        rows = []
        for f in self.floors:
            rows.append((f.name, f.confirmed_length_m, f.confirmed_length_m * self.rate_per_meter))
        return rows


def calculate_budget(floors: list[FloorMeasurement], rate_per_meter: float = DEFAULT_RATE_PER_METER) -> BudgetResult:
    """
    floors: lista de FloorMeasurement com a metragem JA CONFIRMADA por um humano
            (vinda da tela de revisao visual, nao direto do algoritmo).
    """
    total_length = round(sum(f.confirmed_length_m for f in floors), 2)
    total_value = round(total_length * rate_per_meter, 2)
    return BudgetResult(
        floors=floors,
        rate_per_meter=rate_per_meter,
        total_length_m=total_length,
        total_value=total_value,
    )


def format_brl(value: float) -> str:
    """Formata um numero como moeda brasileira: 1234.5 -> 'R$ 1.234,50'"""
    s = f"{value:,.2f}"
    s = s.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {s}"


if __name__ == "__main__":
    # Exemplo com os numeros reais extraidos do arquivo do Gabriel
    # (metragem "alta confianca" usada aqui apenas como demonstracao -
    #  em uso real, o numero confirmado vem da tela de revisao)
    floors = [
        FloorMeasurement("Terreo", confirmed_length_m=305.03, auto_high_confidence_m=305.03, auto_needs_review_m=303.23),
        FloorMeasurement("Pavimento Superior", confirmed_length_m=336.52, auto_high_confidence_m=336.52, auto_needs_review_m=195.04),
        FloorMeasurement("Nivel 2 / Cobertura", confirmed_length_m=30.60, auto_high_confidence_m=30.60, auto_needs_review_m=2.28),
    ]
    result = calculate_budget(floors)
    for name, m, v in result.as_rows():
        print(f"{name:25s} {m:8.2f} m   {format_brl(v)}")
    print("-" * 50)
    print(f"TOTAL: {result.total_length_m} m  x  {format_brl(result.rate_per_meter)}/m  =  {format_brl(result.total_value)}")
