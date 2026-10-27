module Main (main) where

import Batcher
import Console (setupConsole)
import Control.Concurrent (getNumCapabilities, setNumCapabilities)
import Control.Monad (forM_, when)
import Data.Array.IO (IOUArray, newListArray, getElems)
import Data.List (sort)
import GHC.Clock (getMonotonicTime)
import GHC.Conc (getNumProcessors)
import System.Environment (getArgs)
import System.IO
import Text.Printf (printf)
import Text.Read (readMaybe)

-- | Псевдовипадкові числа (лінійний конгруентний генератор), щоб не тягнути пакет random.
randomList :: Int -> Int -> [Int]
randomList seed n = take n (map (`mod` 1000000) (tail (iterate step seed)))
  where step x = (x * 6364136223846793005 + 1442695040888963407) `mod` 9223372036854775783

timeIt :: IO a -> IO (a, Double)
timeIt act = do
  t0 <- getMonotonicTime
  r  <- act
  t1 <- getMonotonicTime
  pure (r, t1 - t0)

-- | Відсортувати копію масиву на k потоках і повернути (результат, час).
runOnce :: Int -> [Int] -> IO ([Int], Double)
runOnce k xs = do
  let n = length xs
  arr <- newListArray (0, n - 1) xs :: IO (IOUArray Int Int)
  (_, t) <- timeIt (sortPar k arr n)
  ys <- getElems arr
  pure (ys, t)

prompt :: String -> IO String
prompt s = putStr s >> hFlush stdout >> getLine

askInt :: String -> (Int -> Bool) -> IO Int
askInt s ok = do
  line <- prompt s
  case readMaybe line of
    Just v | ok v -> pure v
    _ -> putStrLn "  Некоректне значення, спробуйте ще раз." >> askInt s ok

-- | Введення масиву; при помилці — повторний запит.
askArray :: IO [Int]
askArray = do
  line <- prompt "Введіть масив цілих чисел через пробіл (або порожній рядок — згенерувати випадковий): "
  case traverse readMaybe (words line) of
    Just ys@(_:_) -> pure ys
    Just [] -> do
      n <- askInt "Розмір випадкового масиву n = " (> 0)
      pure (randomList 42 n)
    Nothing -> do
      putStrLn "  Не вдалося розібрати числа (потрібні цілі числа через пробіл), спробуйте ще раз."
      askArray

-- | Інтерактивний режим: масив і k вводяться з клавіатури.
interactive :: IO ()
interactive = do
  putStrLn "Сортування Бетчера (обмінне сортування зі злиттям) на k потоках"
  xs <- askArray
  k <- askInt "Кількість потоків k = " (> 0)
  ensureCaps k
  (ys, t) <- runOnce k xs
  let n = length xs
  when (n <= 50) $ do
    putStrLn ("Вхідний масив:      " ++ unwords (map show xs))
    putStrLn ("Відсортований масив: " ++ unwords (map show ys))
  printf "n = %d, k = %d, час сортування: %.4f с\n" n k t
  putStrLn ("Перевірка (збіг з Data.List.sort): " ++ (if ys == sort xs then "OK" else "ПОМИЛКА"))

-- | Переконатися, що RTS має достатньо ядер (capabilities) для k потоків.
ensureCaps :: Int -> IO ()
ensureCaps k = do
  procs <- getNumProcessors
  caps  <- getNumCapabilities
  when (caps < min k procs) $ setNumCapabilities (min k procs)

-- | Режим вимірювання ефективності: n елементів, k = 1, 2, 4, ... до 2*ядер.
bench :: Int -> IO ()
bench n = do
  procs <- getNumProcessors
  setNumCapabilities procs
  printf "Процесорів (ядер): %d, n = %d\n" procs n
  let xs = randomList 7 n
      expected = sort xs
      ks = takeWhile (<= max 2 (2 * procs)) (iterate (* 2) 1)
  _ <- runOnce 1 (take 1000 xs)        -- прогрів
  (_, tList) <- timeIt (pure $! sum (sort xs))
  printf "Data.List.sort (для довідки): %.4f с\n\n" tList
  printf "%4s %10s %12s %12s %6s\n" "k" "час, с" "прискорення" "ефективність" "вірно"
  results <- mapM (measure xs expected) ks
  let t1 = snd (head results)
  forM_ (zip ks results) $ \(k, (ok, t)) ->
    printf "%4d %10.4f %12.2f %11.0f%% %6s\n" k t (t1 / t)
      (100 * t1 / t / fromIntegral (min k procs)) (if ok then "так" else "НІ")
  where
    -- найкращий час із 3 запусків
    measure xs expected k = do
      runs <- mapM (const (runOnce k xs)) [1 .. 3 :: Int]
      pure (all ((== expected) . fst) runs, minimum (map snd runs))

main :: IO ()
main = do
  setupConsole
  args <- getArgs
  case args of
    ["bench"]    -> bench 1000000
    ["bench", s] | Just n <- readMaybe s -> bench n
    _            -> interactive
