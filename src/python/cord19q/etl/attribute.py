"""
StudyModel module
"""

import csv
import os
import sys

import numpy as np
import regex as re
import spacy

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression

from ..models import Models

from .sample import Sample
from .study import StudyModel
from .vocab import Vocab

class Attribute(StudyModel):
    """
    Prediction model used to classify study attributes such as the sample size, sampling method or risk factors.
    """

    def __init__(self):
        """
        Builds a new Attribute detection model.

        Args:
            training: path to training data
            models: path to models
        """

        super(Attribute, self).__init__()

        # Keywords to use as features
        self.keywords = StudyModel.getKeywords(design=False)

        # TF-IDF vectors
        self.tfidf = None

    def predict(self, sections):
        # Build features array for document
        features = [self.features(text, tokens) for name, text, tokens in sections]

        # Build tf-idf vector
        vector = self.tfidf.transform([text for text, _ in features])

        # Concat tf-idf and features vector
        features = np.concatenate((vector.toarray(), [f for _, f in features]), axis=1)

        # Predict probability
        predictions = self.model.predict_proba(features)

        # Ignore predictions for short text snippets
        return [pred if len(sections[x][2]) >= 25 else np.zeros(pred.shape) for x, pred in enumerate(predictions)]

    def create(self):
        return LogisticRegression(C=0.95, fit_intercept=True, penalty="l2", solver="liblinear", max_iter=1000, random_state=0)

    def hyperparams(self):
        return {"C": [x / 20 for x in range(1, 20)],
                "fit_intercept": (True, False),
                "solver": ("lbfgs", "liblinear"),
                "max_iter": (1000,),
                "random_state": 0}

    def data(self, training):
        # Features
        features = []
        labels = []

        # Load NLP model to parse tokens
        nlp = spacy.load("en_core_sci_md")

        # Read training data, convert to features
        with open(training, mode="r") as csvfile:
            for row in csv.DictReader(csvfile):
                # Parse text tokens
                text = row["text"]
                tokens = nlp(text)

                # Store features and labels
                features.append(self.features(text, tokens))
                labels.append(int(row["label"]))

        # Build tf-idf model across dataset, concat with feature vector
        self.tfidf = TfidfVectorizer()
        vector = self.tfidf.fit_transform([text for text, _ in features])
        features = np.concatenate((vector.toarray(), [f for _, f in features]), axis=1)

        print("Loaded %d rows" % len(features))

        return features, labels

    def features(self, text, tokens):
        """
        Builds a features vector from input text.

        Args:
            sections: list of sections

        Returns:
            features vector as a list
        """

        # Build feature vector from regular expressions of common study design terms
        vector = []
        for keyword in self.keywords:
            vector.append(len(re.findall("\\b%s\\b" % keyword.lower(), text.lower())))

        pos = [token.pos_ for token in tokens]
        dep = [token.dep_ for token in tokens]

        # Append entity count (scispacy only tracks generic entities)
        vector.append(len([entity for entity in tokens.ents if entity.text.lower() in self.keywords]))

        # Append part of speech counts
        for name in ["ADJ", "ADP", "ADV", "AUX", "CONJ", "CCONJ", "DET", "INTJ", "NOUN", "NUM", "PART", "PRON", "PUNCT",
                     "SCONJ", "SYM", "VERB", "X", "SPACE"]:
            vector.append(pos.count(name))

        # Append dependency counts
        for name in ["acl", "advcl", "advmod", "amod", "appos", "aux", "case", "cc", "ccomp", "clf", "compound",
                     "conj", "cop", "csubj", "dep", "det", "discourse", "dislocated", "expl", "fixed", "flat",
                     "goeswith", "iobj", "list", "mark", "nmod", "nsubj", "nummod", "obj", "obl", "orphan",
                     "parataxis", "punct", "reparandum", "root", "vocative", "xcomp"]:
            vector.append(dep.count(name))

        # Descriptive numbers on sample identifiers - i.e. 34 patients, 15 subjects, ten samples
        vector.append(1 if Sample.find(tokens, Vocab.SAMPLE) else 0)

        # Regular expression for dates
        dateregex = r"(January|Jan|February|Feb|March|Mar|April|Apr|May|June|Jun|July|Jul|August|Aug|" + \
                    r"September|Sep|October|Oct|November|Nov|December|Dec)\s?\d{1,2}?,? \d{4}?"

        # Dates within the string
        dates = len(re.findall(dateregex, text))
        vector.append(dates)

        return (text, vector)

    @staticmethod
    def run(training, path, optimize):
        """
        Trains a new model.

        Args:
            training: path to training file
            path: models path
            optimize: if hyperparameter optimization should be enabled
        """

        # Default path as it's used for both reading input and the model output path
        if not path:
            path = Models.modelPath()

        # Train the model
        model = Attribute()
        model.train(training, optimize)

        # Save the model
        print("Saving model to %s" % path)
        model.save(os.path.join(path, "attribute"))

if __name__ == "__main__":
    Attribute.run(sys.argv[1] if len(sys.argv) > 1 else None,
                  sys.argv[2] if len(sys.argv) > 2 else None,
                  sys.argv[3] == "1" if len(sys.argv) > 3 else False)
