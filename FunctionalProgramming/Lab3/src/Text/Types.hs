-- | Типи для подання тексту: символ, слово, розділовий знак, речення, текст.
module Text.Types
  ( Symbol (..)
  , Word (..)
  , Punctuation (..)
  , Token (..)
  , Sentence (..)
  , Text (..)
  , symbolChar
  , wordString
  , sentenceWords
  , textWords
  , renderSentence
  , renderText
  ) where

import Prelude hiding (Word)

-- | Символ тексту.
data Symbol
  = Letter Char        -- ^ літера (будь-якої абетки)
  | Digit Char         -- ^ цифра
  | Joiner Char        -- ^ апостроф або дефіс усередині слова (об'єкт, будь-який)
  | Space              -- ^ пробільний символ (пробіл, табуляція, новий рядок)
  | Punct Char         -- ^ розділовий знак
  | Other Char         -- ^ інші символи (оператори в коді: = + * < > ...)
  deriving (Eq, Show)

-- | Слово — непорожня послідовність літер/цифр (з апострофами та дефісами всередині).
newtype Word = Word [Symbol]
  deriving (Eq, Show)

-- | Розділовий знак (або інший неслівний символ).
newtype Punctuation = Punctuation Char
  deriving (Eq, Show)

-- | Лексема речення. Будь-яка послідовність пробілів/табуляцій
--   зберігається як один 'Gap', тобто друкується одним пробілом.
data Token
  = TWord Word
  | TPunct Punctuation
  | Gap
  deriving (Eq, Show)

-- | Речення (пропозиція) — список лексем.
newtype Sentence = Sentence [Token]
  deriving (Eq, Show)

-- | Текст — список речень.
newtype Text = Text [Sentence]
  deriving (Eq, Show)

symbolChar :: Symbol -> Char
symbolChar s = case s of
  Letter c -> c
  Digit c  -> c
  Joiner c -> c
  Space    -> ' '
  Punct c  -> c
  Other c  -> c

wordString :: Word -> String
wordString (Word ss) = map symbolChar ss

sentenceWords :: Sentence -> [Word]
sentenceWords (Sentence ts) = [ w | TWord w <- ts ]

textWords :: Text -> [Word]
textWords (Text ss) = concatMap sentenceWords ss

renderToken :: Token -> String
renderToken t = case t of
  TWord w                -> wordString w
  TPunct (Punctuation c) -> [c]
  Gap                    -> " "

renderSentence :: Sentence -> String
renderSentence (Sentence ts) = concatMap renderToken ts

-- | Текст із нормалізованими пробілами: речення через один пробіл.
renderText :: Text -> String
renderText (Text ss) = unwords (map renderSentence ss)
