from utils.singleton import singleton


@singleton
class singletonTest:
    def __init__(self, name):
        self.name = name

if __name__ == "__main__":
    a = singletonTest("a")
    b = singletonTest("b")
    print(a is b)
