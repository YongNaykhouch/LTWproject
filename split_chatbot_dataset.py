import json
import random
from collections import defaultdict
from pathlib import Path


DATA_DIR = Path(__file__).resolve().parent / 'data'
SOURCE_PATH = DATA_DIR / 'chatbot_training_samples.jsonl'
TRAIN_PATH = DATA_DIR / 'chatbot_train.jsonl'
TEST_PATH = DATA_DIR / 'chatbot_test.jsonl'
TEST_SAMPLES_PER_INTENT = 4
RANDOM_SEED = 20261029


def main():
    records = [
        json.loads(line)
        for line in SOURCE_PATH.read_text(encoding='utf-8').splitlines()
        if line.strip()
    ]
    grouped = defaultdict(list)
    seen_texts = set()

    for record in records:
        if set(record) != {'text', 'intent'}:
            raise ValueError('Each record must contain only text and intent.')
        text = record['text'].strip()
        intent = record['intent'].strip()
        if not text or not intent:
            raise ValueError('Text and intent must not be empty.')
        normalized_text = text.casefold()
        if normalized_text in seen_texts:
            raise ValueError(f'Duplicate sample: {text}')
        seen_texts.add(normalized_text)
        grouped[intent].append({'text': text, 'intent': intent})

    rng = random.Random(RANDOM_SEED)
    training = []
    testing = []
    for intent in sorted(grouped):
        samples = grouped[intent]
        if len(samples) <= TEST_SAMPLES_PER_INTENT:
            raise ValueError(f'Not enough samples for intent: {intent}')
        rng.shuffle(samples)
        testing.extend(samples[:TEST_SAMPLES_PER_INTENT])
        training.extend(samples[TEST_SAMPLES_PER_INTENT:])

    rng.shuffle(training)
    rng.shuffle(testing)
    for path, split in ((TRAIN_PATH, training), (TEST_PATH, testing)):
        path.write_text(
            ''.join(json.dumps(item, ensure_ascii=False) + '\n' for item in split),
            encoding='utf-8',
        )

    print(
        f'Wrote {len(training)} training and {len(testing)} test samples '
        f'across {len(grouped)} intents (seed={RANDOM_SEED}).'
    )


if __name__ == '__main__':
    main()
