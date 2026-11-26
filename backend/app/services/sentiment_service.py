# backend/app/services/sentiment_service.py
"""情感分析服务：词典 + 规则"""
from typing import Tuple, Dict
from enum import Enum

from app.utils.logger import setup_logger

logger = setup_logger(__name__)


class SentimentType(str, Enum):
    POSITIVE = 'positive'
    NEUTRAL = 'neutral'
    NEGATIVE = 'negative'


class SentimentService:
    """情感分析服务"""

    NEGATIVE_WORDS = {
        '非常差': -1.0, '很差': -0.9, '差': -0.8,
        '不满意': -0.7, '失望': -0.7, '生气': -0.9,
        '愤怒': -1.0, '投诉': -0.8, '骗子': -1.0,
        '太差': -0.9, '糟糕': -0.8, '后悔': -0.6,
        '垃圾': -1.0, '恶心': -0.9, '滚': -1.0
    }

    POSITIVE_WORDS = {
        '很好': 0.9, '非常好': 1.0, '棒': 0.8,
        '满意': 0.7, '喜欢': 0.8, '感谢': 0.6,
        '谢谢': 0.5, '好评': 0.8, '推荐': 0.7,
        '划算': 0.6, '便宜': 0.5, '漂亮': 0.7
    }

    NEGATION_WORDS = {'不', '没', '无', '非', '别', '勿'}

    async def analyze(self, text: str) -> Tuple[SentimentType, float]:
        """分析文本情感，返回 (类型, 得分 -1.0 ~ 1.0)"""
        lexicon_score = self._lexicon_analysis(text)
        rule_score = self._rule_analysis(text)
        final_score = max(-1.0, min(1.0, lexicon_score * 0.7 + rule_score * 0.3))
        sentiment_type = self._score_to_type(final_score)
        return sentiment_type, round(final_score, 4)

    def _lexicon_analysis(self, text: str) -> float:
        """词典情感分析"""
        total_score = 0.0
        word_count = 0

        for word, score in {**self.NEGATIVE_WORDS, **self.POSITIVE_WORDS}.items():
            if word in text:
                if self._is_negated(text, word):
                    total_score += score * -0.5
                else:
                    total_score += score
                word_count += 1

        return total_score / word_count if word_count > 0 else 0.0

    def _is_negated(self, text: str, word: str) -> bool:
        for neg in self.NEGATION_WORDS:
            if neg in text:
                idx = text.find(neg)
                w_idx = text.find(word)
                if 0 < w_idx - idx < 5:
                    return True
        return False

    def _rule_analysis(self, text: str) -> float:
        import re
        score = 0.0
        if re.findall(r'(.)\1{2,}', text):
            score += 0.1
        if text.isupper() and len(text) > 3:
            score += 0.2
        score += (text.count('!') + text.count('！')) * 0.05
        return score

    def _score_to_type(self, score: float) -> SentimentType:
        if score <= -0.3:
            return SentimentType.NEGATIVE
        elif score >= 0.3:
            return SentimentType.POSITIVE
        return SentimentType.NEUTRAL

    def get_response_strategy(self, sentiment: SentimentType, score: float) -> Dict:
        strategies = {
            SentimentType.NEGATIVE: {
                'tone': 'empathetic',
                'prefix': '很抱歉给您带来不愉快的体验',
                'action': '建议转人工服务',
                'emoji': '😔'
            },
            SentimentType.NEUTRAL: {
                'tone': 'professional',
                'prefix': '您好',
                'action': '正常服务流程',
                'emoji': '🤖'
            },
            SentimentType.POSITIVE: {
                'tone': 'friendly',
                'prefix': '很高兴为您服务',
                'action': '主动推荐关联服务',
                'emoji': '😊'
            }
        }
        return strategies.get(sentiment, strategies[SentimentType.NEUTRAL])


# 全局单例
sentiment_service = SentimentService()
