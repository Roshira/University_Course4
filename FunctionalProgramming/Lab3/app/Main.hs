module Main (main) where

import Control.Monad (forM_, when)
import System.Environment (getArgs)
import System.Exit (exitFailure)
import System.IO
import Text.Read (readMaybe)
import Text.Parser (parseText)
import Text.Task
import Text.Types
import Console (setupConsole)

data Options = Options
  { optFile   :: FilePath
  , optAll    :: Bool   -- ^ друкувати всі входження слів (за замовчуванням — без повторень)
  , optWidth  :: Int
  , optQuiet  :: Bool   -- ^ не друкувати нормалізований текст
  }

parseArgs :: [String] -> Options -> Maybe Options
parseArgs args o = case args of
  []                    -> Just o
  ("--all" : r)         -> parseArgs r o { optAll = True }
  ("--quiet" : r)       -> parseArgs r o { optQuiet = True }
  ("--width" : n : r)   -> readMaybe n >>= \w -> parseArgs r o { optWidth = w }
  (f : r) | take 2 f /= "--" -> parseArgs r o { optFile = f }
  _                     -> Nothing

readUtf8 :: FilePath -> IO String
readUtf8 path = do
  h <- openFile path ReadMode
  hSetEncoding h utf8
  s <- hGetContents h
  length s `seq` hClose h
  pure s

main :: IO ()
main = do
  setupConsole
  args <- getArgs
  opts <- case parseArgs args (Options "data/textbook.txt" False 80 False) of
    Just o  -> pure o
    Nothing -> do
      putStrLn "Використання: lab3 [файл] [--all] [--width N] [--quiet]"
      exitFailure
  txt@(Text sentences) <- parseText <$> readUtf8 (optFile opts)

  when (not (optQuiet opts)) $ do
    putStrLn ("Текст (табуляції та послідовності пробілів замінено одним пробілом), речень: "
              ++ show (length sentences))
    forM_ (zip [1 :: Int ..] sentences) $ \(i, s) ->
      putStrLn ("  " ++ show i ++ ". " ++ renderSentence s)
    putStrLn ""

  let ws = sortedWords (not (optAll opts)) txt
  putStrLn ("Слова тексту в алфавітному порядку" ++
            (if optAll opts then "" else " (без повторень)") ++ ", кількість: " ++ show (length ws))
  putStrLn ""
  mapM_ putStrLn (formatGroups 4 (optWidth opts) (groupByFirstLetter ws))
