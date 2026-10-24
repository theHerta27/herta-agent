import argparse

from wordcount.counts import summarize


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--text", default="")
    parser.add_argument("--format", choices=("text",), default="text")
    args = parser.parse_args(argv)
    result = summarize(args.text)
    print(f"total={result['total']} unique={result['unique']}")
    for word, count in result["counts"].items():
        print(f"{word}: {count}")


if __name__ == "__main__":
    main()
