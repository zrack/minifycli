//! Deliberately failing pilot fixture. Install only in a disposable snapshot.
//! This is not a defect in the repository being evaluated.

#[test]
fn a_pass_one() {
    assert_eq!(2 + 2, 4);
}

#[test]
fn b_pass_two() {
    assert!("pilot".starts_with('p'));
}

#[test]
fn c_pass_three() {
    assert_eq!([1, 2, 3].len(), 3);
}

#[test]
fn d_pass_four() {
    assert_eq!(Some(7).unwrap_or(0), 7);
}

#[test]
fn z_controlled_failure() {
    println!("✓ migration completed (2 ms)");
    let actual = 42;
    let expected = 41;
    assert_eq!(actual, expected, "MINIFYCLI_PILOT_RUST_ASSERTION");
}
