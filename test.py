s = "aabbcde"

def first_single_str(s):
    counts = {}
    for c in s:
        counts[c] = counts.get(c,0) +1

    for x in s:
        if counts[x] == 1:
            return x
    return None

print(first_single_str(s))



nums = [2,7,11,15]

def two_sum(nums, target):
    for i in range(len(nums)):
        for j in range(i + 1, len(nums)):
            if nums[i] + nums[j] == target:
                return [i, j]
    return None

print(two_sum(nums, 9))

def two_sums(nums, target):
    seen = {}

    for i, num in enumerate(nums):
        diff = target - num

        if diff in seen:
            return [seen[diff], i]

        seen[num] = i

    return None

print(two_sums(nums,9))



def test_brackets(s):
    stack = []
    pairs = {')':'(', ']':'[', '}':'{'}

    for char in s:
        if char in pairs.values():
            stack.append(char)

        elif char in pairs:
            if not stack or stack[-1] != pairs[char]:
                return False
            stack.pop()

    return len(stack) == 0



def count_occurrences(lst):
    count = {}
    for i in lst:
        count[i] = count.get(i,0) + 1

    return count

lst = [1, 2, 2, 3, 3, 3]

print(count_occurrences(lst))



def first_unique_char(s):
    counts = {}
    for c in s:
        counts[c] = counts.get(c,0) + 1

    for c in s:
        if counts[c] == 1:
            return c
    return None

s = "aabbcde"
print(first_unique_char(s))



def two_sum(nums, target):
    seen = {}
    for x, num in enumerate(nums):
        diff = target - num
        if diff in seen:
            return [seen[diff],x]

        seen[num] = x
    return None

print(two_sum([2,7,11,15],9))





def is_valid(s):
    stack = []
    brackets = {')':'(',']':'[','}':'{'}
    for b in s:
        if b in brackets.values():
            stack.append(b)
        elif b in brackets:
            if not stack or stack[-1] != brackets[b]:
                return False
            stack.pop()
    return len(stack) == 0


print(is_valid("([)"))




def longest_substring(s):
    seen = set()
    left = 0
    max_len = 0

    for right in range(len(s)):
        while s[right] in seen:
            seen.remove(s[left])
            left += 1

        seen.add(s[right])
        max_len = max(max_len, right - left + 1)

    return max_len

print(longest_substring("abcdefweedvbhnjjk"))


def remove_duplicates(lst):
    unique = []
    seen = set()
    for c in lst:
        if c not in seen:
            unique.append(c)
            seen.add(c)
    return unique

print(remove_duplicates('abshdkelrltdoooe'))




def is_anagram(s, t):
    if len(s) != len(t):
        return False
    counts = {}

    for c in s:
        counts[c] = counts.get(c,0) + 1

    for c in t:
        if c not in counts:
            return False
        counts[c] -= 1
        if counts[c] < 0:
            return False
    return True



print(is_anagram("listen","silent"))



def is_anagram(s, t):
    if len(s) != len(t):
        return False
    counts = {}
    countt = {}

    for c in s:
        counts[c] = counts.get(c,0) + 1

    for c in t:
        countt[c] = countt.get(c,0) + 1

    for k,v in counts.items():
        if k not in countt or countt[k] != v:
            return False
    return True


print(is_anagram("listen","silent"))



def move_zeros(nums):
    zeros = []
    no_zeros = []
    for num in nums:
        if num != 0:
            no_zeros.append(num)
        else:
            zeros.append(num)
    return no_zeros + zeros

print(move_zeros([0,2,1,4,0,4,6,0,3]))



def move_zeros(nums):
    insert_pos = 0

    for num in nums:
        if num != 0:
            nums[insert_pos] = num
            insert_pos += 1

    for i in range(insert_pos, len(nums)):
        nums[i] = 0

    return nums
print(move_zeros([0,2,1,4,0,4,6,0,3]))



def product_except_self(nums):
    n = len(nums)
    result = [1] *n
    prefix = 1

    for i in range(n):
        result[i] = prefix
        prefix *= nums[i]

    suffix = 1
    for i in range(n-1, -1, -1):
        result[i] *= suffix
        suffix *= nums[i]

    return result

print(product_except_self([1,2,3,4]))


def max_area(height):
    left = 0
    right = len(height)-1
    best = 0

    while left < right:
        width = right -left
        h = min(height[left], height[right])
        area = width * h

        best = max(best, area)

        if height[left] < height[right]:
            left += 1
        else:
            right -= 1
    return best

print(max_area([1,8,6,2,5,4,8,3,7]))







