"""Good implementation of the Travelling Salesman Problem using nearest-neighbor heuristic."""
import math
import random


def distance(city1, city2):
    """Calculates the Euclidean distance between two cities."""
    return math.sqrt((city1[0] - city2[0]) ** 2 + (city1[1] - city2[1]) ** 2)


def test_calc_dist():
    """Tests the calc_dist function."""
    assert distance((0, 0), (3, 4)) == 5.0, "Test failed!"
    assert distance((1, 1), (4, 5)) == 5.0, "Test failed!"
    # assert False
    print("All tests passed!")


def nearest_neighbor(cities):
    """Implements the Nearest Neighbor heuristic for the TSP."""
    current_city = random.choice(cities)  # Start at a random city
    unvisited_cities = set(cities)
    unvisited_cities.remove(current_city)
    tour = [current_city]
    total_distance = 0

    while unvisited_cities:
        nearest_city = None
        min_dist = float("inf")

        for city in unvisited_cities:
            dist = distance(current_city, city)
            if dist < min_dist:
                min_dist = dist
                nearest_city = city

        tour.append(nearest_city)
        total_distance += min_dist
        current_city = nearest_city
        unvisited_cities.remove(current_city)

    # Return to the starting city
    total_distance += distance(current_city, cities[0])
    tour.append(cities[0])

    return tour, total_distance


def main():
    """Runs the nearest-neighbor TSP on a sample set of cities."""
    # Example cities (you can change these)
    cities = [(0, 0), (1, 5), (5, 3), (3, 1), (1, 4), (6, 12), (4, 1), (9, 13), (12, 4), (6, 14)]

    tour, total_distance = nearest_neighbor(cities)

    print("Tour:", tour)
    print("Total Distance:", total_distance)


if __name__ == "__main__":
    main()
