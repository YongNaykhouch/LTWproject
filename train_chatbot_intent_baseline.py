import json
import math
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path


DATA_DIR = Path(__file__).resolve().parent / 'data'
TRAIN_PATH = DATA_DIR / 'chatbot_train.jsonl'
TEST_PATH = DATA_DIR / 'chatbot_blind_test.jsonl'
CORRECTIONS_PATH = DATA_DIR / 'chatbot_training_corrections.jsonl'
MODEL_PATH = DATA_DIR / 'chatbot_intent_baseline.json'
REPORT_PATH = DATA_DIR / 'chatbot_baseline_report.json'
ALPHA = 1.0
CHAR_NGRAM_MIN = 3
CHAR_NGRAM_MAX = 5


def _normalize(text):
    text = text.lower().replace('đ', 'd')
    text = unicodedata.normalize('NFD', text)
    return ''.join(char for char in text if unicodedata.category(char) != 'Mn')


def _features(text):
    normalized = _normalize(text)
    words = re.findall(r'[a-z0-9]+', normalized)
    features = Counter()
    for word in words:
        features['word:' + word] += 1
    for first, second in zip(words, words[1:]):
        features['bigram:' + first + '_' + second] += 1

    compact = re.sub(r'\s+', ' ', normalized).strip()
    padded = '^' + compact + '$'
    for size in range(CHAR_NGRAM_MIN, CHAR_NGRAM_MAX + 1):
        for start in range(max(0, len(padded) - size + 1)):
            features['char:' + padded[start:start + size]] += 1
    return features


def _read_dataset(path):
    records = [
        json.loads(line)
        for line in path.read_text(encoding='utf-8').splitlines()
        if line.strip()
    ]
    if not records:
        raise ValueError(f'Dataset is empty: {path}')
    for record in records:
        if set(record) != {'text', 'intent'}:
            raise ValueError(f'Invalid record in {path}: expected text and intent.')
        if not record['text'].strip() or not record['intent'].strip():
            raise ValueError(f'Empty text or intent in {path}.')
    return records


def _train(records):
    class_documents = Counter()
    class_feature_counts = defaultdict(Counter)
    class_token_totals = Counter()
    vocabulary = set()

    for record in records:
        intent = record['intent']
        features = _features(record['text'])
        class_documents[intent] += 1
        class_feature_counts[intent].update(features)
        class_token_totals[intent] += sum(features.values())
        vocabulary.update(features)

    class_count = len(class_documents)
    total_documents = len(records)
    model = {
        'algorithm': 'multinomial-naive-bayes-word-char-ngram',
        'normalization': 'lowercase, Vietnamese accent folding, word unigrams/bigrams, char 3-5 grams',
        'alpha': ALPHA,
        'classes': {},
    }
    for intent, document_count in sorted(class_documents.items()):
        denominator = class_token_totals[intent] + ALPHA * (len(vocabulary) + 1)
        log_probabilities = {
            feature: math.log((count + ALPHA) / denominator)
            for feature, count in class_feature_counts[intent].items()
        }
        log_unknown = math.log(ALPHA / denominator)
        model['classes'][intent] = {
            'log_prior': math.log(document_count / total_documents),
            'log_unknown': log_unknown,
            'log_feature_probabilities': log_probabilities,
        }
    model['vocabulary_size'] = len(vocabulary)
    model['training_samples'] = total_documents
    return model


def _predict(model, text):
    features = _features(text)
    scores = {}
    for intent, class_model in model['classes'].items():
        probabilities = class_model['log_feature_probabilities']
        score = class_model['log_prior']
        for feature, count in features.items():
            score += count * probabilities.get(feature, class_model['log_unknown'])
        scores[intent] = score
    return max(scores, key=scores.get), scores


def _evaluate(model, records):
    confusion = Counter()
    correct = 0
    misclassified_samples = []
    for record in records:
        predicted, _ = _predict(model, record['text'])
        actual = record['intent']
        confusion[(actual, predicted)] += 1
        if predicted == actual:
            correct += 1
        else:
            misclassified_samples.append({
                'text': record['text'],
                'actual': actual,
                'predicted': predicted,
            })

    intents = sorted(model['classes'])
    per_intent = {}
    for intent in intents:
        true_positive = confusion[(intent, intent)]
        actual_count = sum(count for (actual, _), count in confusion.items() if actual == intent)
        predicted_count = sum(count for (_, predicted), count in confusion.items() if predicted == intent)
        precision = true_positive / predicted_count if predicted_count else 0.0
        recall = true_positive / actual_count if actual_count else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        per_intent[intent] = {
            'support': actual_count,
            'precision': round(precision, 4),
            'recall': round(recall, 4),
            'f1': round(f1, 4),
        }

    errors = [
        {'actual': actual, 'predicted': predicted, 'count': count}
        for (actual, predicted), count in confusion.items()
        if actual != predicted
    ]
    errors.sort(key=lambda item: (-item['count'], item['actual'], item['predicted']))
    return {
        'test_samples': len(records),
        'correct_predictions': correct,
        'accuracy': round(correct / len(records), 4),
        'per_intent': per_intent,
        'misclassifications': errors,
        'misclassified_samples': misclassified_samples,
    }


def main():
    training = _read_dataset(TRAIN_PATH)
    testing = _read_dataset(TEST_PATH)
    corrections = (
        _read_dataset(CORRECTIONS_PATH)
        if CORRECTIONS_PATH.exists()
        else []
    )
    training.extend(corrections)

    training_texts = [record['text'].strip().casefold() for record in training]
    if len(training_texts) != len(set(training_texts)):
        raise ValueError('Training data contains duplicate text.')
    training_texts = set(training_texts)
    testing_texts = {record['text'].strip().casefold() for record in testing}
    if training_texts & testing_texts:
        raise ValueError('Training and test sets contain overlapping text.')
    if {record['intent'] for record in training} != {record['intent'] for record in testing}:
        raise ValueError('Training and test sets must contain the same intents.')

    model = _train(training)
    report = _evaluate(model, testing)
    model['evaluation'] = {
        'test_samples': report['test_samples'],
        'accuracy': report['accuracy'],
    }
    model['training_correction_samples'] = len(corrections)
    MODEL_PATH.write_text(
        json.dumps(model, ensure_ascii=False, indent=2) + '\n',
        encoding='utf-8',
    )
    REPORT_PATH.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + '\n',
        encoding='utf-8',
    )

    print(
        f"Baseline accuracy: {report['accuracy']:.1%} "
        f"({report['test_samples']} test samples)"
    )
    print(f"Model: {MODEL_PATH.name}; report: {REPORT_PATH.name}")
    if report['misclassifications']:
        print('Misclassifications:')
        for error in report['misclassified_samples']:
            print(
                f"  {error['actual']} -> {error['predicted']}: "
                f"{ascii(error['text'])}"
            )
    else:
        print('No misclassifications in the current test split.')


if __name__ == '__main__':
    main()
