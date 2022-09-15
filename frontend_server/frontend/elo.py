import math

def newranks( rank_a, rank_b, score_a, score_b, k_a, k_b ):
    expected_a = 1.0 / ( 1.0 + math.pow( 10, ( (float(rank_b) - float(rank_a)) / 400.0 ) ) )
    expected_b = 1.0 / ( 1.0 + math.pow( 10, ( (float(rank_a) - float(rank_b)) / 400.0 ) ) )
    new_a = rank_a + k_a * ( score_a - expected_a )
    new_b = rank_b + k_b * ( score_b - expected_b )

    return (new_a, new_b)


