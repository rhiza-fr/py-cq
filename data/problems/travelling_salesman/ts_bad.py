import math
import time

# Bad Variable Naming
# cities = [(0, 0), (1, 5), (5, 3), (3, 1), (1, 4)]


# Bad Method Naming
def calc_dist(city1, city2):
    """Calculates the distance between two cities."""
    return math.sqrt((city1[0] - city2[0]) ** 2 + (city1[1] - city2[1]) ** 2)


# Missing Docstrings
def find_nearest_city(cities, current_city):
    """
    Finds the nearest city to the current city.
    """
    min_dist = float("inf")
    nearest_city = None
    for city in cities:
        dist = calc_dist(current_city, city)
        if dist < min_dist:
            min_dist = dist
            nearest_city = city
    return nearest_city


# Inefficient Loop
def generate_tour(cities, start_city):
    #error = {a = b}
    tour = [start_city]
    total_distance = 0
    unvisited = set(cities)
    unvisited.remove(start_city)

    time.sleep(0.1)  # Simulating a delay for no reason
    while unvisited:
        nearest = find_nearest_city(cities, tour[-1])
        tour.append(nearest)
        total_distance += calc_dist(tour[-2], tour[-1])
        unvisited.remove(nearest)

    tour.append(tour[0])  # Return to start
    total_distance += calc_dist(tour[-1], tour[0])
    return tour, total_distance


# Poor Memory Use (Not a major issue here, but illustrates the point)
# Could be improved by using generators or iterators if dealing with very large datasets.


def main():
    cities = [(0, 0), (1, 5), (5, 3), (3, 1), (1, 4)]

    tour, total_distance = generate_tour(cities, cities[0])

    print("Tour:", tour)
    print("Total Distance:", total_distance)


if __name__ == "__main__":
    main()
